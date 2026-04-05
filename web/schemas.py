"""Pydantic models for API request/response validation."""

from typing import List, Optional

from pydantic import BaseModel


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    message: str
    administrations: list


class JobCreateRequest(BaseModel):
    admin_id: str
    job_type: str = "data"  # data, files, both
    endpoints: List[str] = []
    years: List[int] = []  # empty = all years


class JobResponse(BaseModel):
    id: str
    admin_id: str
    admin_name: str
    job_type: str
    status: str
    endpoints: list
    completed_steps: list
    current_step: Optional[str] = None
    items_exported: int = 0
    items_total: Optional[int] = None
    error_message: Optional[str] = None
    data_dir: Optional[str] = None
    created_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


class StepResponse(BaseModel):
    step_name: str
    status: str
    items_count: int = 0
    items_total: Optional[int] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
