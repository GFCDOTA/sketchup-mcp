"""Registry determinístico de módulos por cômodo; carrega metadados, nunca builders.

Não importa bedroom/kitchen/... na consulta. Resolve alias de cômodo por catálogo.
Capacidades declaradas descrevem código existente; não autorizam execução.
"""
from __future__ import annotations

import json
from pathlib import Path

MANIFEST = Path(__file__).with_name("manifest.v1.json")
ROOM_ALIASES = {
    "living_room": "living", "living": "living", "sala": "living",
    "bedroom": "bedroom", "quarto": "bedroom", "suite": "bedroom",
    "kitchen": "kitchen", "cozinha": "kitchen",
    "bathroom": "bathroom", "banheiro": "bathroom", "lavabo": "bathroom",
    "service": "service", "laundry": "service", "lavanderia": "service",
    "balcony": "balcony", "varanda": "balcony", "terraco": "balcony",
    "closet": "closet", "home_office": "home_office",
    "circulation": "circulation", "corredor": "circulation",
}


def load_manifest(path: Path = MANIFEST) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if (data.get("schema_version") != "fp041_room_modules.v1"
            or data.get("policy") != "READ_ONLY_ROUTING_NO_DYNAMIC_IMPORT_OR_SKP_WRITES"):
        raise ValueError("INVALID_ROOM_MODULE_POLICY")
    if not data.get("rooms") or not data.get("shared"):
        raise ValueError("INCOMPLETE_ROOM_MODULE_REGISTRY")
    for key, record in data["rooms"].items():
        if record.get("package") != "tools.rooms." + key or record.get("execution_authorized") is not False:
            raise ValueError("INVALID_ROOM_MODULE_" + key)
    return data


def resolve_module(room_type: str) -> dict:
    if not isinstance(room_type, str):
        raise TypeError("room_type must be a string")
    key = ROOM_ALIASES.get(room_type.strip().lower())
    if key is None:
        raise KeyError("UNSUPPORTED_ROOM_TYPE")
    data = load_manifest()
    return {"room": key, **data["rooms"][key], "shared": data["shared"]}


def resolve_project_room(alias_or_room_id: str, project_id: str = "planta_74") -> dict:
    from core.domain.room_registry import room_info
    record = room_info(alias_or_room_id, project_id=project_id)
    return {
        "room_id": record.room_id,
        "display_name": record.display_name,
        "module": resolve_module(record.room_type),
    }
