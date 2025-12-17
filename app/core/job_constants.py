from typing import Final, Literal

JobStatus = Literal["queued", "started", "finished", "failed"]

JobStage = Literal[
    "downloading",
    "analyzing",
    "cutting",
    "uploading_clip",
    "done",
]

STATUS_QUEUED: Final[JobStatus] = "queued"
STATUS_STARTED: Final[JobStatus] = "started"
STATUS_FINISHED: Final[JobStatus] = "finished"
STATUS_FAILED: Final[JobStatus] = "failed"

STAGE_DOWNLOADING: Final[JobStage] = "downloading"
STAGE_ANALYZING: Final[JobStage] = "analyzing"
STAGE_CUTTING: Final[JobStage] = "cutting"
STAGE_UPLOADING: Final[JobStage] = "uploading_clip"
STAGE_DONE: Final[JobStage] = "done"
