"""FastAPI backend for CodePilot Agent."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from app.agent.graph import build_graph
from app.agent.run import stream_agent, _configure_langsmith
from app.config import get_settings
from app.llm.provider import get_llm_provider
from app.logging_config import get_logger


class AgentRequest(BaseModel):
    """Request to run the agent."""

    task: str = Field(..., description="The task to execute")
    existing_code: str = Field(default="", description="Existing code to modify")
    extra_constraints: str = Field(default="", description="Additional constraints")


class AgentResponse(BaseModel):
    """Response from the agent."""

    status: str
    iteration: int
    next_action: str | None
    reasoning_summary: str
    code: str
    tests: str
    final_answer: str | None
    trace: list[dict[str, Any]]
    task_type: str
    requirements: list[str]
    constraints: list[str]
    acceptance_criteria: list[str]
    edge_cases: list[str]
    plan: dict[str, Any]
    test_results: dict[str, Any]
    verification_result: dict[str, Any]
    error_analysis: dict[str, Any]
    errors: list[str]
    tags: list[str] = Field(default_factory=list)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle."""
    logger = get_logger("api")
    logger.info("Starting CodePilot API")
    _configure_langsmith()
    yield
    logger.info("Shutting down CodePilot API")


app = FastAPI(
    title="CodePilot Agent API",
    description="Autonomous code engineering system",
    version="0.1.0",
    lifespan=lifespan,
)

logger = get_logger("api")


@app.get("/")
async def root():
    """Root endpoint."""
    return {"message": "CodePilot Agent API", "version": "0.1.0"}


@app.get("/health")
async def health():
    """Health check endpoint."""
    settings = get_settings()
    return {
        "status": "healthy",
        "model": settings.llm_model,
        "api_key_configured": bool(settings.groq_api_key.strip()),
        "max_iterations": settings.max_iterations,
    }


@app.post("/run", response_model=AgentResponse)
async def run_agent(request: AgentRequest) -> AgentResponse:
    """Run the agent on a task."""
    settings = get_settings()
    
    if not settings.groq_api_key.strip():
        raise HTTPException(status_code=400, detail="GROQ_API_KEY not configured")
    
    try:
        logger.info(f"Running agent on task: {request.task[:100]}...")
        
        # Build initial tags for this run
        tags = ["codepilot", "python"]
        if request.existing_code.strip():
            tags.append("modify")
        else:
            tags.append("build")
        if request.extra_constraints.strip():
            tags.append("constrained")
        
        # Run the agent synchronously (FastAPI runs in async context)
        final_snapshot = {}
        for snapshot in stream_agent(
            request.task,
            existing_code=request.existing_code,
            extra_constraints=request.extra_constraints,
            tags=tags,
        ):
            final_snapshot = snapshot
        
        # Add final status tags
        if final_snapshot:
            final_status = final_snapshot.get("status")
            if final_status == "verified":
                tags.append("success")
            elif final_status == "failed":
                tags.append("failure")
            else:
                tags.append("incomplete")
            
            if final_snapshot.get("iteration") >= settings.max_iterations:
                tags.append("max_iterations")
            
            final_snapshot["tags"] = tags
        
        return AgentResponse(**final_snapshot)
        
    except Exception as exc:
        logger.error(f"Agent execution failed: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/run/stream")
async def run_agent_stream(request: AgentRequest):
    """Run the agent with streaming responses."""
    settings = get_settings()
    
    if not settings.groq_api_key.strip():
        raise HTTPException(status_code=400, detail="GROQ_API_KEY not configured")
    
    async def event_generator():
        try:
            # Build initial tags for this run
            tags = ["codepilot", "python"]
            if request.existing_code.strip():
                tags.append("modify")
            else:
                tags.append("build")
            if request.extra_constraints.strip():
                tags.append("constrained")
            
            for snapshot in stream_agent(
                request.task,
                existing_code=request.existing_code,
                extra_constraints=request.extra_constraints,
                tags=tags,
            ):
                yield f"data: {snapshot}\n\n"
        except Exception as exc:
            logger.error(f"Agent execution failed: {exc}")
            yield f"data: {{'error': '{str(exc)}'}}\n\n"
    
    return app.send_event_generator(event_generator(), media_type="text/event-stream")
