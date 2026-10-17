from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

CONFIG_VERSION = 2
SUPPORTED_CONFIG_VERSIONS = (1, 2)
DEFAULT_MID_SAMPLE_NS = 10_000_000


class ExecConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    maker_fee: float = 0.0002
    taker_fee: float = 0.0005
    entry_latency_ns: int = 10_000_000
    resp_latency_ns: int = 10_000_000
    queue_model: Literal["power_prob", "risk_adverse"] = "power_prob"
    queue_power: float = 2.0
    partial_fill: bool = False


class RunConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    strategy: str
    data_files: list[str]
    initial_snapshot: str | None = None
    tick_size: float
    lot_size: float
    step_ns: int = 100_000_000
    mid_sample_ns: int = DEFAULT_MID_SAMPLE_NS
    order_qty: float = 0.001
    max_position: float = 0.01
    params: dict = {}
    exec: ExecConfig = ExecConfig()

    @model_validator(mode="after")
    def _check_mid_sample(self) -> "RunConfig":
        if self.mid_sample_ns <= 0 or self.step_ns % self.mid_sample_ns != 0:
            raise ValueError(
                f"step_ns {self.step_ns} must be a positive multiple of "
                f"mid_sample_ns {self.mid_sample_ns}"
            )
        return self


class RunRecord(BaseModel):
    config_version: int = CONFIG_VERSION
    git_commit: str
    git_dirty: bool
    hftbacktest_version: str
    config: RunConfig
