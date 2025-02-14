import httpx
from typing import Dict, Any
from urllib.parse import quote
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SMSService:
    def __init__(self):
        self.BASE_URL = "https://smartsms.nettyfish.com/api/v2/SendSMS"
        logger.info("SMS Service initialized")

    async def send_sms(self, phone_number: str, message: str, config: Dict[str, Any]) -> Dict[str, Any]:
        try:
            if not all(key in config for key in ['ApiKey', 'ClientId', 'SenderId']):
                raise Exception("Missing required SMS configuration")

            if not message:
                raise Exception("Message content is required")

            logger.info("Preparing to send SMS to: %s", phone_number)
            
            # Clean up phone number
            cleaned_phone = phone_number.replace("91", "", 1) if phone_number.startswith("91") else phone_number
            logger.info("Cleaned phone number: %s", cleaned_phone)
            
            # URL encode the message and phone number
            encoded_message = quote(message)
            encoded_phone = quote(cleaned_phone)

            # Construct the URL with config from node
            url = (
                f"{self.BASE_URL}?"
                f"ApiKey={config['ApiKey']}&"
                f"ClientId={config['ClientId']}&"
                f"MobileNumbers={encoded_phone}&"
                f"SenderId={config['SenderId']}&"
                f"Message={encoded_message}&"
                f"Is_Flash=false&"
                f"Is_Unicode=false"
            )

            # Send the request
            logger.info("Sending HTTP request to SMS gateway...")
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url)
                response.raise_for_status()
                logger.info("SMS gateway response received: %s", response.text)

                # Check for specific error codes in response
                response_data = response.json()
                if response_data.get("ErrorCode") != 0:
                    raise Exception(f"SMS Gateway Error: {response_data.get('ErrorDescription')}")
                
                # Check message-level errors
                for data in response_data.get("Data", []):
                    if data.get("MessageErrorCode") != 0:
                        raise Exception(f"Message Error: {data.get('MessageErrorDescription')}")
                    
                    # Log the actual mobile number used by the gateway
                    actual_mobile = data.get("MobileNumber", "")
                    logger.info("Gateway processed mobile number: %s", actual_mobile)
                    logger.info("Message ID: %s", data.get("MessageId"))

            logger.info("SMS sent successfully to %s", cleaned_phone)
            return {
                "status": "success",
                "message": "SMS sent successfully",
                "details": {
                    "to": cleaned_phone,
                    "response": response.text,
                    "messageId": response_data.get("Data", [{}])[0].get("MessageId")
                }
            }

        except Exception as e:
            logger.error("Failed to send SMS: %s", str(e))
            return {
                "status": "error",
                "message": str(e)
            }

    # def get_message(self) -> str:
    #     """Return the exact SMS content"""
    #     message = (
    #         "Thank you for buying Quality Assured Medicines at QnQ Pharmacy on 05-01-2025 07:32. "
    #         "Invoice CINV-0038/RO/0010296/24-25 Rs 15.00. "
    #         "If not, pls call/Whatsapp +91 95977 06555. "
    #         "View E-Invoice @ https://qnqhealthcare.com/Brch1/einv.html?id=NzM1NzI0&bid=38&te=RO "
    #         "QnQ Healthcare Pvt Ltd"
    #     )
    #     logger.info("Generated SMS message: %s", message)
    #     return message 