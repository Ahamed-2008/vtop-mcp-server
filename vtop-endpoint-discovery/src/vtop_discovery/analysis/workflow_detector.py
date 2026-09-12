from __future__ import annotations

from typing import Any
from urllib.parse import parse_qsl

from vtop_discovery.analysis.deduplicator import compute_endpoint_signature, _generate_endpoint_id
from vtop_discovery.storage.models import CapturedExchange, Endpoint, Workflow, WorkflowDependency

IGNORE_DEPENDENCY_PARAMS = {
    "x",
    "_",
    "timestamp",
    "time",
    "t",
    "nocache",
    "password",
    "passwd",
    "captcha",
    "authorizedid",
    "_csrf",
}


def _extract_param_names_and_values(data: Any) -> dict[str, str]:
    out: dict[str, str] = {}
    if not data:
        return out
    if isinstance(data, dict):
        for k, v in data.items():
            out[str(k)] = str(v)
    elif isinstance(data, str):
        if "=" in data and "&" in data:
            for k, v in parse_qsl(data, keep_blank_values=True):
                out[k] = v
    return out


def detect_workflows(exchanges: list[CapturedExchange], endpoints_map: dict[str, Endpoint] | None = None) -> list[Workflow]:
    """Detect multi-step workflows and data dependencies between successive VTOP requests."""
    if not exchanges:
        return []

    # Map each exchange to its stable endpoint_id
    exchange_endpoints: list[tuple[CapturedExchange, str]] = []
    for ex in exchanges:
        sig = compute_endpoint_signature(ex)
        method, path, q_keys, b_keys = sig
        ep_id = _generate_endpoint_id(method, path, q_keys, b_keys)
        exchange_endpoints.append((ex, ep_id))

    workflows_by_key: dict[tuple[str, ...], Workflow] = {}
    
    # Track producers in a sliding window
    # Keep history of produced parameters: field_name -> (producing_endpoint_id, values_list)
    recent_producers: dict[str, list[tuple[str, list[str]]]] = {}

    for i, (exchange, ep_id) in enumerate(exchange_endpoints):
        req_params = dict(exchange.request.query)
        req_params.update(_extract_param_names_and_values(exchange.request.body))

        dependencies: list[WorkflowDependency] = []
        producing_steps: set[str] = set()

        for param_name, param_val in req_params.items():
            lowered = param_name.lower()
            if lowered in IGNORE_DEPENDENCY_PARAMS:
                continue

            # Check if this parameter was produced by a previous step
            if param_name in recent_producers:
                # Find most recent producer
                for prod_ep_id, prod_values in reversed(recent_producers[param_name]):
                    if prod_ep_id != ep_id:
                        # Value match or field name match
                        if not prod_values or param_val in prod_values or any(param_val in pv for pv in prod_values):
                            dependencies.append(
                                WorkflowDependency(
                                    parameter=param_name,
                                    produced_by=prod_ep_id,
                                    consumed_by=ep_id,
                                )
                            )
                            producing_steps.add(prod_ep_id)
                            break
                        elif param_name.lower() in {"semestersubid", "categoryid", "paramreturnid", "semsubid", "empid", "classgroupid"}:
                            dependencies.append(
                                WorkflowDependency(
                                    parameter=param_name,
                                    produced_by=prod_ep_id,
                                    consumed_by=ep_id,
                                )
                            )
                            producing_steps.add(prod_ep_id)
                            break

        if producing_steps and dependencies:
            steps = list(producing_steps) + [ep_id]
            wf_key = tuple(steps)
            if wf_key not in workflows_by_key:
                workflows_by_key[wf_key] = Workflow(
                    name=f"workflow_{len(workflows_by_key) + 1}",
                    steps=steps,
                    dependencies=dependencies,
                )
            else:
                # Merge dependencies
                existing_wf = workflows_by_key[wf_key]
                existing_params = {d.parameter for d in existing_wf.dependencies}
                for dep in dependencies:
                    if dep.parameter not in existing_params:
                        existing_wf.dependencies.append(dep)

        # Now register anything this response produces
        if exchange.response and exchange.response.body:
            from vtop_discovery.analysis.response_analyzer import parse_html_response, parse_json_response

            resp_body = exchange.response.body
            c_type = (exchange.response.content_type or "").lower()
            analysis = None
            if isinstance(resp_body, (dict, list)):
                analysis = parse_json_response(resp_body)
            elif isinstance(resp_body, str):
                if "json" in c_type:
                    try:
                        import json
                        analysis = parse_json_response(json.loads(resp_body))
                    except Exception:
                        pass
                if not analysis and ("html" in c_type or ("<" in resp_body and ">" in resp_body)):
                    analysis = parse_html_response(resp_body)

            if analysis and analysis.produced_fields:
                for field_name, values in analysis.produced_fields.items():
                    if field_name not in recent_producers:
                        recent_producers[field_name] = []
                    recent_producers[field_name].append((ep_id, values))

    return list(workflows_by_key.values())
