"""
GitHub Webhook Handler for Vanish Compute (VNC)
Automates creation and cleanup of preview environments from GitHub events
"""
import hmac
import hashlib
import logging
import os
from typing import Dict, Any
from fastapi import APIRouter, Request, Header, HTTPException, Depends

from src.main import platform

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks/github", tags=["webhooks"])

# Secret for verifying GitHub webhook signatures
GITHUB_WEBHOOK_SECRET = os.getenv("GITHUB_WEBHOOK_SECRET")

async def verify_signature(request: Request, x_hub_signature_256: str = Header(None)):
    """Verify that the webhook request came from GitHub"""
    if not GITHUB_WEBHOOK_SECRET:
        return # Skip verification if secret not set
        
    if not x_hub_signature_256:
        raise HTTPException(status_code=401, detail="X-Hub-Signature-256 missing")
        
    body = await request.body()
    signature = "sha256=" + hmac.new(
        GITHUB_WEBHOOK_SECRET.encode(),
        body,
        hashlib.sha256
    ).hexdigest()
    
    if not hmac.compare_digest(signature, x_hub_signature_256):
        raise HTTPException(status_code=401, detail="Invalid signature")

@router.post("/events", dependencies=[Depends(verify_signature)])
async def handle_github_event(request: Request, x_github_event: str = Header(...)):
    """Main event handler for GitHub webhooks"""
    payload = await request.json()
    
    logger.info(f"Received GitHub event: {x_github_event}")
    
    if x_github_event == "pull_request":
        return await _handle_pull_request(payload)
    
    return {"status": "ignored"}

async def _handle_pull_request(payload: Dict[str, Any]):
    """Handle pull_request events: opened, synchronized, closed"""
    action = payload.get("action")
    pr_data = payload.get("pull_request", {})
    repo_data = payload.get("repository", {})
    
    repo_url = repo_data.get("clone_url")
    repo_ref = pr_data.get("head", {}).get("ref")
    pr_number = payload.get("number")
    
    if action in ["opened", "reopened", "synchronize"]:
        logger.info(f"Creating/Updating preview for PR #{pr_number}")
        # Logic to either update existing or create new
        session_id = await platform.create_preview_environment(
            repo_url=str(repo_url),
            repo_ref=str(repo_ref),
            pr_number=int(pr_number) if pr_number is not None else 0
        )
        return {"status": "provisioning", "session_id": session_id}
        
    elif action == "closed":
        logger.info(f"Cleaning up preview for closed PR #{pr_number}")
        # Find session associated with this PR and destroy it
        for session in list(platform.session_manager.sessions.values()):
            if session.pr_number == pr_number and session.repo_url == repo_url:
                await platform.destroy_session(session.id)
        return {"status": "cleanup_triggered"}

    return {"status": "action_ignored"}
