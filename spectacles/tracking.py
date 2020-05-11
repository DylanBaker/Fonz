import analytics  # type: ignore
import hashlib
import uuid

analytics.write_key = "QnqzXWlqkmgDSm7X2qFDrxx3LGCW7Rba"


def anonymise(trait: str) -> str:
    trait = hashlib.md5(trait.encode()).hexdigest()
    return trait


def track_invocation_start(
    base_url: str, command: str, project: str, invocation_id: str = str(uuid.uuid4())
) -> str:
    url_hash = anonymise(base_url.rstrip("/"))
    project_hash = anonymise(project)
    analytics.track(
        user_id=url_hash,
        event="invocation",
        properties={
            "label": "start",
            "command": command,
            "project": project_hash,
            "invocation_id": invocation_id,
        },
    )
    return invocation_id


def track_invocation_end(base_url: str, command: str, project: str, invocation_id: str):
    url_hash = anonymise(base_url.rstrip("/"))
    project_hash = anonymise(project)
    analytics.track(
        user_id=url_hash,
        event="invocation",
        properties={
            "label": "end",
            "command": command,
            "project": project_hash,
            "invocation_id": invocation_id,
        },
    )
