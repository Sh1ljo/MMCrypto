from typing import Literal

from pydantic import BaseModel, ConfigDict

CONFIG_VERSION = 1


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
    order_qty: float = 0.001
    max_position: float = 0.01
    params: dict = {}
    exec: ExecConfig = ExecConfig()


class RunRecord(BaseModel):
    config_version: int = CONFIG_VERSION
    git_commit: str
    git_dirty: bool
    hftbacktest_version: str
    config: RunConfig
