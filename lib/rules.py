#!/usr/bin/env python3
"""Rule-based routing: domains, IPs, CIDRs."""

import ipaddress
import json
import re
import socket
from typing import Dict, List, Set, Tuple

from lib.logger import log
from lib.paths import RUNTIME_DIR

RULES_CACHE = RUNTIME_DIR / "rules_cache.json"

DOMAIN_RE = re.compile(
    r"^(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}$"
)


def is_ip(value: str) -> bool:
    try:
        ipaddress.ip_address(value)
        return True
    except ValueError:
        return False


def is_cidr(value: str) -> bool:
    try:
        ipaddress.ip_network(value, strict=False)
        return True
    except ValueError:
        return False


def is_domain(value: str) -> bool:
    return bool(DOMAIN_RE.match(value))


def normalize_rule(rule: str) -> str:
    return rule.strip().lower()


def resolve_domain(domain: str) -> List[str]:
    ips: Set[str] = set()
    try:
        for info in socket.getaddrinfo(domain, None, socket.AF_INET):
            ips.add(info[4][0])
    except socket.gaierror:
        log.warning(f"Could not resolve domain: {domain}")
    return sorted(ips)


def expand_rule(rule: str) -> List[str]:
    """Expand a rule entry to list of IP/CIDR strings."""
    rule = normalize_rule(rule)

    if is_cidr(rule) or is_ip(rule):
        return [rule]

    if is_domain(rule):
        ips = resolve_domain(rule)
        return ips

    log.warning(f"Invalid routing rule ignored: {rule}")
    return []


def expand_rules(rules: List[str]) -> Tuple[List[str], Dict[str, List[str]]]:
    """Expand all rules; return flat targets and domain->ips map."""
    targets: List[str] = []
    domain_map: Dict[str, List[str]] = {}

    for rule in rules or []:
        rule = normalize_rule(rule)
        if is_domain(rule):
            ips = resolve_domain(rule)
            domain_map[rule] = ips
            targets.extend(ips)
        else:
            expanded = expand_rule(rule)
            targets.extend(expanded)

    # Deduplicate preserving order
    seen: Set[str] = set()
    unique = []
    for t in targets:
        if t not in seen:
            seen.add(t)
            unique.append(t)

    return unique, domain_map


def load_rules_config(config: Dict) -> Dict:
    routing = config.get("routing", {})
    return {
        "mode": routing.get("mode", "full"),
        "include": routing.get("include", routing.get("rules", [])),
        "exclude": routing.get("exclude", []),
        "split": routing.get("split", []),
    }


def save_rules_cache(domain_map: Dict):
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    RULES_CACHE.write_text(json.dumps(domain_map, indent=2))


def load_rules_cache() -> Dict:
    if not RULES_CACHE.exists():
        return {}
    try:
        return json.loads(RULES_CACHE.read_text())
    except json.JSONDecodeError:
        return {}

