import logging

# Configure basic logger to verify notifications in terminal during development
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("AmalNotificationAdapter")

def send_push_notification(donor_id: str, title: str, body: str, data: dict = None) -> bool:
    """
    Sends a high-priority push notification. 
    Simulated in development. Can be wired to FCM or OneSignal API.
    """
    payload = {
        "to_donor_id": donor_id,
        "title": title,
        "body": body,
        "priority": "high",
        "data": data or {}
    }
    
    # Development logging simulation (equivalent to push notifications on emulator)
    logger.info(f"\n⚡ [PUSH NOTIFICATION SENT] {payload}\n")
    return True
