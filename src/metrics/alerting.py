import logging
from typing import Dict, Any, Optional
from datetime import datetime
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class Alert:
    """Represents a system alert"""
    id: str
    severity: str  # critical, warning, info
    title: str
    description: str
    timestamp: datetime
    metadata: Dict[str, Any]

class AlertManager:
    """Manages system alerts and external integrations"""
    
    def __init__(self):
        self.active_alerts: Dict[str, Alert] = {}
        self.pagerduty_key: Optional[str] = None
        self.opsgenie_key: Optional[str] = None
        self.logger = logging.getLogger(__name__)

    def configure_pagerduty(self, api_key: str):
        self.pagerduty_key = api_key

    def configure_opsgenie(self, api_key: str):
        self.opsgenie_key = api_key

    async def trigger_alert(self, severity: str, title: str, description: str, metadata: Dict[str, Any] = None):
        """Trigger an alert and notify external providers"""
        alert_id = f"alert-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{hash(title) % 10000}"
        alert = Alert(
            id=alert_id,
            severity=severity,
            title=title,
            description=description,
            timestamp=datetime.now(),
            metadata=metadata or {}
        )
        
        self.active_alerts[alert_id] = alert
        self.logger.error(f"ALERT [{severity.upper()}]: {title} - {description}")

        # Send to external providers (simulated)
        if self.pagerduty_key:
            await self._send_to_pagerduty(alert)
        if self.opsgenie_key:
            await self._send_to_opsgenie(alert)

    async def resolve_alert(self, alert_id: str):
        """Mark an alert as resolved"""
        if alert_id in self.active_alerts:
            alert = self.active_alerts.pop(alert_id)
            self.logger.info(f"Alert RESOLVED: {alert.title}")

    async def _send_to_pagerduty(self, alert: Alert):
        self.logger.info(f"Forwarding alert to PagerDuty: {alert.title}")
        # Real implementation would use httpx.post to PD Events API

    async def _send_to_opsgenie(self, alert: Alert):
        self.logger.info(f"Forwarding alert to OpsGenie: {alert.title}")
        # Real implementation would use httpx.post to OpsGenie Alerts API


_alert_manager: Optional[AlertManager] = None

def get_alert_manager() -> AlertManager:
    """Get the global alert manager instance"""
    global _alert_manager
    if _alert_manager is None:
        _alert_manager = AlertManager()
    return _alert_manager
