from typing import Dict, Any, List
from datetime import datetime
from app.db.supabase import supabase_client
from app.schemas.workflow import ExecutionStatus, NodeExecution
from app.services.gmail_service import GmailService
from fastapi_mail import ConnectionConfig, FastMail, MessageSchema
from app.services.sms_service import SMSService
from app.services.chatgpt_service import ChatGPTService
from app.services.slack_service import SlackService
import logging
import re
import operator
from decimal import Decimal
from uuid import uuid4

# Configure logging at the top of the file
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    force=True  # Force reconfiguration of the root logger
)
logger = logging.getLogger(__name__)

class WorkflowExecutor:
    def __init__(self, workflow_execution: Dict[str, Any]):
        self.execution = workflow_execution
        self.workflow_id = workflow_execution['workflow_id']
        self.execution_id = workflow_execution['id']
        self.gmail_service = GmailService()
        self.sms_service = SMSService()
        self.chatgpt_service = ChatGPTService()
        self.slack_service = SlackService()
        # Storage for node outputs and workflow structure
        self.node_outputs = {}
        self.sms_config = None
        self.workflow_nodes = []  # Will hold workflow nodes
        self.workflow_edges = []  # Will hold workflow edges
        logger.info("WorkflowExecutor initialized")

    async def start(self):
        try:
            # Update execution status to running
            await self._update_execution_status(ExecutionStatus.RUNNING)

            # Get workflow definition and store nodes/edges for event handling
            workflow = await self._get_workflow()
            if not workflow:
                raise Exception("Workflow not found")
            self.workflow_nodes = workflow.get("nodes", [])
            self.workflow_edges = workflow.get("edges", [])

            # Get starting nodes (nodes with no incoming edges)
            start_nodes = self._get_start_nodes(workflow['nodes'], workflow['edges'])
            
            # Execute workflow in topological order
            visited = set()
            for node in start_nodes:
                await self._execute_node_chain(node, workflow['edges'], workflow['nodes'], visited)

            # Update execution status to completed
            await self._update_execution_status(ExecutionStatus.COMPLETED)

        except Exception as e:
            # Update execution status to failed
            await self._update_execution_status(
                ExecutionStatus.FAILED,
                error_message=str(e)
            )
            raise e

    async def _execute_node_chain(self, node: Dict[str, Any], edges: List[Dict[str, Any]], 
                                nodes: List[Dict[str, Any]], visited: set):
        """Execute nodes in topological order following the graph structure"""
        if node['id'] in visited:
            return
        
        # Mark node as visited
        visited.add(node['id'])
        
        try:
            # Execute current node
            output = await self._execute_node(node, self.execution['trigger_data']['data'], self.node_outputs)
            self.node_outputs[node['id']] = output

            # Get and execute all next nodes
            next_nodes = self._get_next_nodes(node['id'], edges, nodes)
            for next_node in next_nodes:
                # Check if all incoming edges' source nodes have been executed
                incoming_edges = [edge for edge in edges if edge['target'] == next_node['id']]
                all_dependencies_met = all(edge['source'] in visited for edge in incoming_edges)
                
                if all_dependencies_met:
                    await self._execute_node_chain(next_node, edges, nodes, visited)

        except Exception as e:
            logger.error(f"Error executing node {node['id']}: {str(e)}")
            raise e

    async def _execute_node(
        self,
        node: Dict[str, Any],
        form_data: Dict[str, Any],
        node_outputs: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute a single node with access to previous node outputs"""
        try:
            logger.info(f"\n=== Executing Node ===")
            logger.info(f"Node ID: {node.get('id')}")
            logger.info(f"Node Type: {node.get('type')}")
            logger.info(f"Node Data: {node.get('data')}")
            logger.info(f"Form Data: {form_data}")
            logger.info(f"Available Node Outputs: {node_outputs}")

            node_execution = await self._create_node_execution(node['id'])
            
            try:
                node_type = node.get("type")
                if node_type == "action":
                    app_id = node.get("data", {}).get("app", {}).get("id")
                    logger.info(f"Executing action node with app: {app_id}")

                    if app_id == "mailConfig":
                        # Store mail config for later use
                        config = node.get("data", {}).get("config", {}).get("mailConfig", {})
                        self.mail_config = config
                        result = {
                            "status": "success",
                            "message": "Mail configuration saved"
                        }
                        await self._update_node_execution(
                            node_execution['id'],
                            ExecutionStatus.COMPLETED,
                            output_data=result
                        )
                        return result

                    elif app_id == "mail":
                        if not hasattr(self, 'mail_config'):
                            raise Exception("Mail configuration not found. Please add a Mail Config node first.")
                        
                        config = node.get("data", {}).get("config", {})
                        to_address = self._process_template(config.get("to", ""), form_data)
                        subject = config.get("subject", "")
                        content = config.get("content", "")

                        # Check if there's a connected ChatGPT node and get its output
                        chatgpt_content = None
                        chatgpt_subject = None
                        for node_id, output in node_outputs.items():
                            if isinstance(output, dict):
                                if "content" in output:
                                    chatgpt_content = output.get("content", "")
                                if "subject" in output:
                                    chatgpt_subject = output.get("subject", "")

                        # Replace ChatGPT placeholders in subject and content
                        if chatgpt_subject and "{{chatgpt_subject}}" in subject:
                            subject = subject.replace("{{chatgpt_subject}}", chatgpt_subject)
                            logger.info(f"Replaced ChatGPT subject: {subject}")

                        if chatgpt_content and "{{chatgpt}}" in content:
                            content = content.replace("{{chatgpt}}", chatgpt_content)
                            logger.info(f"Replaced ChatGPT content: {content}")

                        # Process any remaining form field placeholders
                        subject = self._process_template(subject, form_data)
                        content = self._process_template(content, form_data)
                        
                        if not content:
                            raise Exception("No content available to send")

                        # Merge mail config with node config
                        mail_config = {
                            **self.mail_config,
                            "to": to_address,
                            "subject": subject,
                            "content": content
                        }
                        
                        # Send email using the Gmail service
                        result = await self.gmail_service.send_email(
                            config=mail_config,
                            form_data=form_data
                        )
                        
                        await self._update_node_execution(
                            node_execution['id'],
                            ExecutionStatus.COMPLETED if result["status"] == "success" else ExecutionStatus.FAILED,
                            output_data=result
                        )
                        await self._emit_event("mail_completed", node, result)
                        return result

                    elif app_id == "chatgpt":
                        config = node.get("data", {}).get("config", {}).get("chatgptConfig", {})
                        result = await self._execute_chatgpt_action(node)
                        
                        # Add subject to the result if not present
                        if "subject" not in result and "content" in result:
                            # Extract first line as subject and remove it from content
                            content = result["content"]
                            lines = content.split('\n', 1)  # Split only at first newline
                            
                            # First line becomes subject (max 100 chars)
                            subject = lines[0][:100].strip()
                            
                            # Rest becomes content (or empty if no newlines)
                            body = lines[1].strip() if len(lines) > 1 else ""
                            
                            # Update the result
                            result["subject"] = subject
                            result["content"] = body
                            
                            logger.info(f"Extracted subject: {subject}")
                            logger.info(f"Remaining content: {body}")
                        
                        await self._update_node_execution(
                            node_execution['id'],
                            ExecutionStatus.COMPLETED,
                            output_data=result
                        )
                        return result

                    elif app_id == "slack":
                        config = node.get("data", {}).get("config", {}).get("slackConfig", {})
                        # Replace placeholders in message with node outputs and form data
                        message = config.get("message", "")
                        
                        # First replace form data placeholders
                        message = self.replace_placeholders(message, form_data)
                        
                        # Then replace node output placeholders
                        for node_id, output in node_outputs.items():
                            if isinstance(output, dict):
                                # For ChatGPT output
                                if "content" in output:
                                    placeholder = "{{chatgpt}}"  # Special handling for chatgpt placeholder
                                    if placeholder in message:
                                        message = message.replace(placeholder, output["content"])
                                # For other node outputs
                                for key, value in output.items():
                                    placeholder = f"{{{{{node_id}.{key}}}}}"
                                    if placeholder in message:
                                        message = message.replace(placeholder, str(value))
                        
                        config["message"] = message
                        logger.info(f"Slack config after placeholder replacement: {config}")
                        
                        result = await self.slack_service.send_message(
                            webhook_url=config.get("webhook_url", ""),
                            channel=config.get("channel", ""),
                            message=config.get("message", "")
                        )
                        await self._update_node_execution(
                            node_execution['id'],
                            ExecutionStatus.COMPLETED,
                            output_data=result
                        )
                        return result

                    elif app_id == "smsConfig":
                        config = node.get("data", {}).get("config", {}).get("smsConfig", {})
                        if not all(key in config for key in ['ApiKey', 'ClientId', 'SenderId']):
                            raise Exception("Incomplete SMS configuration")
                        
                        # Store SMS config for use by SMS action nodes
                        self.sms_config = config
                        
                        result = {
                            "status": "success",
                            "message": "SMS configuration saved"
                        }
                        
                        await self._update_node_execution(
                            node_execution['id'],
                            ExecutionStatus.COMPLETED,
                            output_data=result
                        )
                        return result

                    elif app_id == "sms":
                        if not hasattr(self, 'sms_config'):
                            raise Exception("SMS configuration not found. Please add an SMS Config node first.")
                        
                        config = node.get("data", {}).get("config", {}).get("smsMessage", {})
                        if not config:
                            raise Exception("SMS message configuration not found")
                        
                        # Process template variables
                        to_number = self._process_template(config.get("to", ""), form_data)
                        message = self._process_template(config.get("message", ""), form_data)
                        
                        # Send SMS using the SMS service
                        result = await self.sms_service.send_sms(
                            phone_number=to_number,
                            message=message,
                            config=self.sms_config
                        )
                        
                        await self._update_node_execution(
                            node_execution['id'],
                            ExecutionStatus.COMPLETED,
                            output_data=result
                        )
                        return result

                    elif app_id == "math":
                        # Execute math node and log calculated result
                        result = await self._execute_math_action(node)
                        await self._update_node_execution(
                            node_execution['id'],
                            ExecutionStatus.COMPLETED,
                            output_data=result
                        )
                        return result

                # Default case for unsupported node types
                result = {
                    "status": "skipped",
                    "reason": f"Unsupported node type: {node_type}"
                }
                await self._update_node_execution(
                    node_execution['id'],
                    ExecutionStatus.COMPLETED,
                    output_data=result
                )
                return result

            except Exception as e:
                await self._update_node_execution(
                    node_execution['id'],
                    ExecutionStatus.FAILED,
                    error_message=str(e)
                )
                raise e

        except Exception as e:
            logger.error(f"Node execution failed: {str(e)}")
            return {
                "status": "failed",
                "error": str(e)
            }

    def _get_previous_node_outputs(self, node_id: str, edges: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Get outputs from all incoming nodes"""
        incoming_edges = [edge for edge in edges if edge['target'] == node_id]
        previous_outputs = {}
        
        for edge in incoming_edges:
            source_id = edge['source']
            if source_id in self.node_outputs:
                previous_outputs[source_id] = self.node_outputs[source_id]
        
        return previous_outputs

    async def _execute_action_node(self, node: Dict[str, Any], previous_outputs: Dict[str, Any]) -> Dict[str, Any]:
        """Execute an action node based on its type"""
        try:
            node_type = node.get('data', {}).get('app', {}).get('id')
            
            # Get form data from the workflow execution
            form_data = self.execution.get('trigger_data', {}).get('data', {})

            if node_type == 'mail':
                # Get mail configuration
                mail_config = node.get('data', {}).get('config', {})
                to_address = self._process_template(mail_config.get('to', ''), form_data)
                subject = self._process_template(mail_config.get('subject', ''), form_data)
                content = mail_config.get('content', '')

                # Check if there's a connected ChatGPT node and get its output
                workflow = await self._get_workflow()
                chatgpt_content = None
                for source_node_id, output in self.node_outputs.items():
                    source_node = next(
                        (n for n in workflow['nodes'] 
                         if n['id'] == source_node_id and 
                         n.get('data', {}).get('app', {}).get('id') == 'chatgpt'),
                        None
                    )
                    if source_node:
                        chatgpt_content = output.get('content', '')
                        break

                # If content contains {{chatgpt}} placeholder and ChatGPT content exists
                if chatgpt_content:
                    content = content.replace('{{chatgpt}}', chatgpt_content)

                # Process any remaining form field placeholders
                content = self._process_template(content, form_data)

                if not content:
                    raise Exception("No content available to send")

                # Send email
                result = await self.gmail_service.send_email(
                    to=to_address,
                    subject=subject,
                    body=content,
                    config=self.mail_config
                )
                return result
            elif node_type == 'sms':
                return await self._execute_sms_action(node)
            elif node_type == 'chatgpt':
                chatgpt_config = node.get('data', {}).get('config', {}).get('chatgptConfig', {})
                result = await self.chatgpt_service.generate_content(chatgpt_config, form_data)
                self.node_outputs[node['id']] = result
                return result
            elif node_type == 'mailConfig':
                return await self._execute_mail_config_action(node)
            elif node_type == 'smsConfig':
                return await self._execute_sms_config_action(node)
            elif node_type == 'slack':
                # Get Slack configuration
                slack_config = node.get('data', {}).get('config', {}).get('slackConfig', {})
                webhook_url = slack_config.get('webhook_url')
                channel = slack_config.get('channel')
                message = slack_config.get('message')

                # Check if there's a connected ChatGPT node and get its output
                workflow = await self._get_workflow()
                chatgpt_content = None
                for source_node_id, output in self.node_outputs.items():
                    source_node = next(
                        (n for n in workflow['nodes'] 
                         if n['id'] == source_node_id and 
                         n.get('data', {}).get('app', {}).get('id') == 'chatgpt'),
                        None
                    )
                    if source_node:
                        chatgpt_content = output.get('content', '')
                        break

                # If message contains {{chatgpt}} placeholder or is empty and ChatGPT content exists
                if chatgpt_content:
                    message = message or chatgpt_content  # Use message if exists, otherwise use ChatGPT content
                    message = message.replace('{{chatgpt}}', chatgpt_content)  # Replace placeholder if exists

                # Replace any form field placeholders in the message
                message = self.replace_placeholders(message, form_data)

                if not message:
                    raise Exception("No message content available to send")

                # Send Slack message
                result = await self.slack_service.send_message(
                    webhook_url=webhook_url,
                    channel=channel,
                    message=message
                )
                return result
            elif node_type == 'math':
                return await self._execute_math_action(node)
            else:
                raise Exception(f"Unsupported action type: {node_type}")

        except Exception as e:
            logger.error(f"Action node execution failed: {str(e)}")
            raise Exception(f"Action node execution failed: {str(e)}")

    def _get_next_nodes(self, node_id: str, edges: List[Dict[str, Any]], nodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Get all nodes that should be executed after the current node"""
        next_node_ids = [
            edge['target']
            for edge in edges
            if edge['source'] == node_id
        ]
        return [
            node for node in nodes
            if node['id'] in next_node_ids
        ]

    async def _get_workflow(self) -> Dict[str, Any]:
        response = supabase_client.table('workflows')\
            .select('*')\
            .eq('id', self.workflow_id)\
            .single()\
            .execute()
        return response.data

    async def _execute_form_node(self, node: Dict[str, Any]) -> Dict[str, Any]:
        # For now, just pass through the form data from trigger
        return self.execution['trigger_data']

    async def _execute_email_action(self, node: Dict[str, Any]) -> Dict[str, Any]:
        try:
            # First find the mail config node
            workflow = await self._get_workflow()
            mail_config_node = next(
                (node for node in workflow['nodes'] 
                 if node.get('data', {}).get('app', {}).get('id') == 'mailConfig'),
                None
            )
            
            if not mail_config_node:
                raise Exception("Mail configuration not found. Please add a Mail Config node.")

            # Get mail config settings
            mail_settings = mail_config_node.get('data', {}).get('config', {}).get('mailConfig', {})
            if not all([mail_settings.get(key) for key in ['host', 'port', 'username', 'password']]):
                raise Exception("Incomplete mail configuration. Please check Mail Config node settings.")

            # Get the node's configuration
            node_config = node.get('data', {}).get('config', {})
            form_data = self.execution.get('trigger_data', {}).get('data', {})

            # Find connected ChatGPT node output
            chatgpt_content = None
            for source_node_id, output in self.node_outputs.items():
                source_node = next(
                    (n for n in workflow['nodes'] 
                     if n['id'] == source_node_id and 
                     n.get('data', {}).get('app', {}).get('id') == 'chatgpt'),
                    None
                )
                if source_node and output.get('status') == 'success':
                    chatgpt_content = output.get('content')
                    break

            # If content is empty and ChatGPT content is available, use it
            if not node_config.get('content') and chatgpt_content:
                node_config['content'] = chatgpt_content
            elif '{{chatgpt}}' in node_config.get('content', ''):
                # Replace {{chatgpt}} placeholder with generated content
                node_config['content'] = node_config['content'].replace('{{chatgpt}}', chatgpt_content or '')

            # Create mail configuration using node settings
            mail_conf = ConnectionConfig(
                MAIL_USERNAME=mail_settings['username'],
                MAIL_PASSWORD=mail_settings['password'],
                MAIL_FROM=mail_settings['username'],
                MAIL_PORT=int(mail_settings['port']),
                MAIL_SERVER=mail_settings['host'],
                MAIL_STARTTLS=True,
                MAIL_SSL_TLS=False,
                USE_CREDENTIALS=True
            )

            # Create FastMail instance with dynamic config
            fastmail = FastMail(mail_conf)

            # Prepare email data
            email_config = {
                "from": mail_settings['username'],
                "to": node_config.get('to', ''),
                "subject": node_config.get('subject', 'Workflow Notification'),
                "body": node_config.get('content', 'Form submitted')
            }

            if not email_config['to']:
                raise Exception("No recipient email address found")

            # Process templates for all fields
            for field_name, field_value in form_data.items():
                placeholder = f"{{{{{field_name}}}}}"
                for key in ['to', 'subject', 'body']:
                    if placeholder in email_config[key]:
                        email_config[key] = email_config[key].replace(placeholder, str(field_value))

            # Validate email address after placeholder replacement
            if not '@' in email_config['to']:
                raise Exception(f"Invalid email address: {email_config['to']}")

            # Create message
            message = MessageSchema(
                subject=email_config['subject'],
                recipients=[email_config['to']],
                body=email_config['body'],
                subtype="plain"
            )

            # Send email
            await fastmail.send_message(message)

            return {
                "status": "success",
                "message": "Email sent successfully",
                "details": {
                    "from": email_config['from'],
                    "to": email_config['to'],
                    "subject": email_config['subject'],
                    "body": email_config['body']
                }
            }

        except Exception as e:
            raise Exception(f"Mail action failed: {str(e)}")

    async def _execute_sms_action(self, node: Dict[str, Any]) -> Dict[str, Any]:
        try:
            logger.info("Starting SMS action execution for node: %s", node.get('id'))
            
            # First find the SMS config node
            workflow = await self._get_workflow()
            sms_config_node = next(
                (node for node in workflow['nodes'] 
                 if node.get('data', {}).get('app', {}).get('id') == 'smsConfig'),
                None
            )
            
            if not sms_config_node:
                logger.error("SMS configuration node not found")
                raise Exception("SMS configuration not found. Please add an SMS Config node.")

            # Get SMS config settings
            sms_settings = sms_config_node.get('data', {}).get('config', {}).get('smsConfig', {})
            if not all([sms_settings.get(key) for key in ['ApiKey', 'ClientId', 'SenderId']]):
                logger.error("Incomplete SMS configuration")
                raise Exception("Incomplete SMS configuration. Please check SMS Config node settings.")

            # Get the node's configuration and form data
            node_config = node.get('data', {}).get('config', {}).get('smsMessage', {})
            form_data = self.execution.get('trigger_data', {}).get('data', {})
            
            # Get phone number from form data if it contains a placeholder
            phone_number = node_config.get('to', '')
            if '{{' in phone_number and '}}' in phone_number:
                field_name = phone_number.strip('{}')
                phone_number = form_data.get(field_name, '')
            
            if not phone_number:
                raise Exception("No valid phone number found")

            # Get message content and process any placeholders
            message = node_config.get('message', '')
            for field_name, field_value in form_data.items():
                placeholder = f"{{{{{field_name}}}}}"
                if placeholder in message:
                    message = message.replace(placeholder, str(field_value))
            
            if not message:
                raise Exception("No message content found")
            
            logger.info("Sending SMS to: %s", phone_number)

            # Send SMS with dynamic message and config
            result = await self.sms_service.send_sms(
                phone_number, 
                message,
                sms_settings
            )
            logger.info("SMS action completed with result: %s", result)

            return result

        except Exception as e:
            logger.error("SMS action failed: %s", str(e))
            raise Exception(f"SMS action failed: {str(e)}")

    async def _execute_mail_config_action(self, node: Dict[str, Any]) -> Dict[str, Any]:
        try:
            config = node.get('data', {}).get('config', {})
            return {
                "status": "success",
                "message": "Mail configuration updated",
                "config": {
                    "host": config.get('host'),
                    "port": config.get('port'),
                    "username": config.get('username'),
                    "password": config.get('password')
                }
            }
        except Exception as e:
            raise Exception(f"Failed to execute mail config action: {str(e)}")

    async def _execute_sms_config_action(self, node: Dict[str, Any]) -> Dict[str, Any]:
        """Execute SMS configuration action"""
        try:
            logger.info("Processing SMS configuration for node: %s", node.get('id'))
            
            # Get the SMS configuration from the node
            sms_config = node.get('data', {}).get('config', {}).get('smsConfig', {})
            if not sms_config:
                raise Exception("SMS configuration not found")

            # Store the configuration in node outputs for use by SMS action nodes
            config_output = {
                "status": "success",
                "message": "SMS configuration processed successfully",
                "config": sms_config
            }

            self.node_outputs[node['id']] = config_output
            return config_output

        except Exception as e:
            logger.error("SMS config action failed: %s", str(e))
            raise Exception(f"SMS config action failed: {str(e)}")

    async def _execute_math_action(self, node: Dict[str, Any]) -> Dict[str, Any]:
        try:
            config = node.get('data', {}).get('config', {}).get('mathConfig', {})
            if not config:
                raise ValueError("Math configuration not found")

            operation = config.get('operation')
            inputs = config.get('inputs', {})
            form_data = self.execution.get('trigger_data', {}).get('data', {})
            output_variable = config.get('outputVariable', 'result')
            include_details = config.get('includeDetails', False)
            
            print("\n" + "="*50)
            print(f"Math Function Execution")
            print("="*50)
            print(f"Operation Type: {operation}")
            print(f"Output Variable: {output_variable}")
            print("-"*50)

            def get_value(input_str: str, default: str = '0') -> float:
                if not input_str:
                    return float(default)
                if input_str.startswith('{{') and input_str.endswith('}}'):
                    field_name = input_str[2:-2]
                    value = form_data.get(field_name)
                    if value is None:
                        raise ValueError(f"Field {field_name} not found in form data")
                    print(f"Field value for {field_name}: {value}")
                    try:
                        return float(value)
                    except (ValueError, TypeError):
                        raise ValueError(f"Field '{field_name}' value '{value}' cannot be converted to number")
                print(f"Direct value: {input_str}")
                return float(input_str)

            # Handle custom formula operation
            if operation == 'custom':
                formula = config.get('customFormula', '')
                if not formula:
                    raise ValueError("Custom formula is empty")

                print("Custom Formula Calculation:")
                print(f"Original Formula: {formula}")
                
                processed_formula = formula
                for field_name, field_value in form_data.items():
                    placeholder = f'{{{{{field_name}}}}}'
                    if placeholder in processed_formula:
                        try:
                            numeric_value = float(field_value)
                            processed_formula = processed_formula.replace(placeholder, str(numeric_value))
                        except (ValueError, TypeError):
                            raise ValueError(f"Field '{field_name}' value '{field_value}' cannot be converted to number")

                print(f"Processed Formula: {processed_formula}")
                
                if not re.match(r'^[\d\s\+\-\*\/\(\)\.]+$', processed_formula):
                    raise ValueError("Invalid characters in formula")

                result = float(eval(processed_formula))
                details = {
                    "formula": formula,
                    "processed_formula": processed_formula,
                    "result": result
                }
                print(f"Result: {result}")

            # Handle basic operations
            elif operation in ['add', 'subtract', 'multiply', 'divide', 'power']:
                value1 = get_value(inputs.get('value1', '0'))
                value2 = get_value(inputs.get('value2', '0'))
                
                print("Basic Operation Calculation:")
                print(f"Value 1: {value1}")
                print(f"Value 2: {value2}")
                print(f"Operation: {operation}")
                
                ops = {
                    'add': operator.add,
                    'subtract': operator.sub,
                    'multiply': operator.mul,
                    'divide': operator.truediv,
                    'power': operator.pow
                }
                
                result = ops[operation](value1, value2)
                details = {
                    'value1': value1,
                    'value2': value2,
                    'operation': operation,
                    'result': result
                }
                print(f"Result: {result}")

            # Handle GST calculation
            elif operation == 'gst':
                value1 = get_value(inputs.get('value1', '0'))
                rate = float(inputs.get('taxRate', '0'))
                
                print("GST Calculation:")
                print(f"Base Amount: {value1}")
                print(f"GST Rate: {rate}%")
                
                tax_amount = (value1 * rate) / 100
                result = value1 + tax_amount
                details = {
                    'base_amount': value1,
                    'rate': rate,
                    'tax_amount': tax_amount,
                    'total': result
                }
                print(f"GST Amount: {tax_amount}")
                print(f"Total (with GST): {result}")

            # Handle discount calculation
            elif operation == 'discount':
                value = get_value(inputs.get('value1', '0'))
                rate = float(inputs.get('discountRate', '0'))
                
                print("Discount Calculation:")
                print(f"Original Amount: {value}")
                print(f"Discount Rate: {rate}%")
                
                discount_amount = (value * rate) / 100
                result = value - discount_amount
                details = {
                    'original_amount': value,
                    'discount_rate': rate,
                    'discount_amount': discount_amount,
                    'final_amount': result
                }
                print(f"Discount Amount: {discount_amount}")
                print(f"Final Amount (after discount): {result}")

            # Round the result if specified
            round_decimals = config.get('roundDecimals')
            if round_decimals is not None:
                result = round(result, int(round_decimals))
                logger.info(f"Rounded to {round_decimals} decimal places: {result}")

            print("-"*50)
            logger.info(f"Final Output: {result}")
            logger.info(f"Stored in variable: {output_variable}")
            print("="*50 + "\n")

            return {
                "status": "success",
                "result": result,
                "outputVariable": output_variable,
                "details": details if include_details else None
            }

        except Exception as e:
            print(f"Math operation failed: {str(e)}")
            return {
                "status": "error",
                "message": f"Math operation failed: {str(e)}"
            }

    def _perform_basic_operation(self, operation: str, value1: float, value2: float) -> float:
        operations = {
            'add': lambda x, y: x + y,
            'subtract': lambda x, y: x - y,
            'multiply': lambda x, y: x * y,
            'divide': lambda x, y: x / y if y != 0 else float('inf'),
            'power': lambda x, y: pow(x, y),
            'root': lambda x, y: pow(x, 1/y) if y != 0 else float('inf'),
            'min': lambda x, y: min(x, y),
            'max': lambda x, y: max(x, y),
            'average': lambda x, y: (x + y) / 2,
            'absolute': lambda x, _: abs(x),
            'percentage': lambda x, y: (x * y) / 100,
        }
        
        if operation not in operations:
            raise ValueError(f"Unsupported operation: {operation}")
            
        return operations[operation](value1, value2)

    async def _create_node_execution(self, node_id: str) -> Dict[str, Any]:
        """Create a node execution record"""
        try:
            execution_data = {
                "id": str(uuid4()),
                "workflow_execution_id": self.execution_id,
                "node_id": node_id,
                "status": ExecutionStatus.RUNNING,
                "started_at": datetime.utcnow().isoformat()
            }
            
            # Remove await since supabase_client is synchronous
            response = supabase_client.table("node_executions")\
            .insert(execution_data)\
            .execute()
            
            if not response.data:
                raise Exception("Failed to create node execution record")
            
            return response.data[0]
        
        except Exception as e:
            logger.error(f"Failed to create node execution: {str(e)}")
            raise e

    async def _update_node_execution(
        self,
        execution_id: str,
        status: str,
        output_data: Dict[str, Any] = None,
        error_message: str = None
    ) -> None:
        """Update a node execution record"""
        try:
            update_data = {
                "status": status,
                "completed_at": datetime.utcnow().isoformat()
            }
            
            if output_data is not None:
                update_data["output_data"] = output_data
            if error_message is not None:
                update_data["error_message"] = error_message

            # Remove await since supabase_client is synchronous
            response = supabase_client.table("node_executions")\
            .update(update_data)\
                .eq("id", execution_id)\
            .execute()
            
            if not response.data:
                raise Exception("Failed to update node execution record")
            
        except Exception as e:
            logger.error(f"Failed to update node execution: {str(e)}")
            raise e

    async def _update_execution_status(
        self,
        status: ExecutionStatus,
        error_message: str = None
    ):
        update_data = {
            "status": status,
            "completed_at": datetime.utcnow().isoformat()
        }
        if error_message:
            update_data["error_message"] = error_message

        supabase_client.table('workflow_executions')\
            .update(update_data)\
            .eq('id', self.execution_id)\
            .execute()

    def _get_start_nodes(
        self,
        nodes: List[Dict[str, Any]],
        edges: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        target_nodes = set(edge['target'] for edge in edges)
        return [node for node in nodes if node['id'] not in target_nodes]

    def _get_action_config(self, node_id: str) -> Dict[str, Any] | None:
        try:
            response = supabase_client.table('action_configurations')\
                .select('*')\
                .eq('workflow_id', self.workflow_id)\
                .eq('node_id', node_id)\
                .execute()
            
            if response.data and len(response.data) > 0:
                return response.data[0]
            return None
        
        except Exception:
            return None

    async def _execute_chatgpt_action(self, node: Dict[str, Any]) -> Dict[str, Any]:
        try:
            logger.info("Starting ChatGPT action execution for node: %s", node.get('id'))
            
            # Get the node's configuration
            chatgpt_config = node.get('data', {}).get('config', {}).get('chatgptConfig', {})
            if not chatgpt_config.get('apiKey'):
                raise Exception("ChatGPT API key not found in configuration")

            # Get form data
            form_data = self.execution.get('trigger_data', {}).get('data', {})
            if not form_data:
                raise Exception("No form data available for content generation")

            # Generate content using ChatGPT service
            result = await self.chatgpt_service.generate_content(
                config=chatgpt_config,
                form_data=form_data
            )

            logger.info("ChatGPT action completed with result: %s", result)
            return result

        except Exception as e:
            logger.error("ChatGPT action failed: %s", str(e))
            raise Exception(f"ChatGPT action failed: {str(e)}")

    def replace_placeholders(self, message: str, form_data: dict) -> str:
        for field_name, field_value in form_data.items():
            placeholder = f"{{{{{field_name}}}}}"
            message = message.replace(placeholder, str(field_value))
        return message

    async def execute_workflow(
        self,
        nodes: List[Dict[str, Any]],
        edges: List[Dict[str, Any]],
        trigger_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        try:
            logger.info("\n=== Starting Workflow Execution ===")
            logger.info(f"Raw trigger data: {trigger_data}")
            
            form_submission_data = trigger_data.get('data', {})
            logger.info(f"Extracted form data: {form_submission_data}")

            self.node_outputs = {}
            execution_results = {}
            processed_nodes = set()
            processed_edges = set()
            skipped_nodes = set()  # Track nodes that were skipped due to conditions

            trigger_node = next(
                (node for node in nodes if node["type"] == "form"),
                None
            )
            
            if not trigger_node:
                logger.error("No trigger node found in workflow")
                raise ValueError("No trigger node found in workflow")

            logger.info(f"Found trigger node: {trigger_node['id']}")
            
            processed_nodes.add(trigger_node["id"])
            self.node_outputs[trigger_node["id"]] = form_submission_data
            execution_results[trigger_node["id"]] = {
                "status": "completed",
                "data": form_submission_data
            }

            while True:
                next_edge = self._find_next_valid_edge(edges, processed_nodes, processed_edges)
                if not next_edge:
                    logger.info("No more valid edges to process")
                    break

                edge_id = next_edge.get("id")
                if edge_id in processed_edges:
                    logger.warning(f"Edge {edge_id} already processed, skipping to prevent loop")
                    continue

                logger.info(f"\nProcessing edge: {next_edge}")
                source_node_id = next_edge["source"]
                target_node_id = next_edge["target"]

                # Skip if source node was skipped due to conditions
                if source_node_id in skipped_nodes:
                    logger.info(f"Skipping node {target_node_id} - parent node {source_node_id} was skipped")
                    skipped_nodes.add(target_node_id)  # Also skip this node
                    processed_nodes.add(target_node_id)
                    processed_edges.add(edge_id)
                    execution_results[target_node_id] = {
                        "status": "skipped",
                        "reason": "Parent node was skipped"
                    }
                    continue

                # Validate target node exists
                target_node = next((node for node in nodes if node["id"] == target_node_id), None)
                if not target_node:
                    logger.warning(f"Target node {target_node_id} not found, skipping edge")
                    processed_edges.add(edge_id)
                    continue
                
                # Evaluate edge conditions
                conditions_met = self._evaluate_edge_conditions(next_edge, form_submission_data)
                logger.info(f"Conditions evaluation result for node {target_node_id}: {conditions_met}")

                if not conditions_met:
                    logger.info(f"Skipping node {target_node_id} - conditions not met")
                    skipped_nodes.add(target_node_id)  # Add to skipped nodes
                    processed_nodes.add(target_node_id)
                    processed_edges.add(edge_id)
                    execution_results[target_node_id] = {
                        "status": "skipped",
                        "reason": "Conditions not met"
                    }
                    continue

                # Execute node with access to previous node outputs
                logger.info(f"Executing node: {target_node_id}")
                result = await self._execute_node(target_node, form_submission_data, self.node_outputs)
                execution_results[target_node_id] = result
                self.node_outputs[target_node_id] = result
                processed_nodes.add(target_node_id)
                processed_edges.add(edge_id)

            logger.info("\n=== Workflow Execution Completed ===")
            return {
                "status": "completed",
                "results": execution_results,
                "executed_at": datetime.utcnow().isoformat()
            }

        except Exception as e:
            logger.error(f"Workflow execution failed: {str(e)}")
            return {
                "status": "failed",
                "error": str(e),
                "executed_at": datetime.utcnow().isoformat()
            }

    def _find_next_valid_edge(
        self,
        edges: List[Dict[str, Any]],
        processed_nodes: set,
        processed_edges: set
    ) -> Dict[str, Any]:
        """Find the next valid edge where source is processed but target isn't"""
        for edge in edges:
            edge_id = edge.get("id")
            if (edge_id not in processed_edges and
                edge["source"] in processed_nodes and 
                edge["target"] not in processed_nodes):
                return edge
        return None

    def _evaluate_edge_conditions(
        self,
        edge: Dict[str, Any],
        form_data: Dict[str, Any]
    ) -> bool:
        """Evaluate conditions on an edge"""
        try:
            logger.info("\n=== Starting Edge Condition Evaluation ===")
            logger.info(f"Edge: {edge['source']} -> {edge['target']}")
            logger.info(f"Form data: {form_data}")
            
            conditions = edge.get("data", {}).get("conditions", [])
            logger.info(f"Conditions to evaluate: {conditions}")
            
            if not conditions:
                logger.info("No conditions found - executing node by default")
                return True

            for condition in conditions:
                # Remove {{ }} and any extra spaces
                field = condition["field"].strip("{}").strip()
                operator = condition["operator"]
                expected_value = str(condition["value"]).strip()
                actual_value = str(form_data.get(field, "")).strip()
                
                logger.info(f"\nEvaluating condition:")
                logger.info(f"Field: '{field}'")
                logger.info(f"Operator: '{operator}'")
                logger.info(f"Expected value: '{expected_value}'")
                logger.info(f"Actual value: '{actual_value}'")

                result = self._check_condition(actual_value, operator, expected_value)
                logger.info(f"Condition result: {result}")

                if not result:
                    logger.info("Condition failed - skipping node execution")
                    return False

            logger.info("All conditions passed")
            return True

        except Exception as e:
            logger.error(f"Error evaluating conditions: {str(e)}")
            return False

    def _check_condition(
        self,
        actual_value: str,
        operator: str,
        expected_value: str
    ) -> bool:
        """Check a single condition"""
        try:
            logger.info(f"Checking: '{actual_value}' {operator} '{expected_value}'")

            # Ensure we're comparing strings
            actual_value = str(actual_value).strip()
            expected_value = str(expected_value).strip()

            if operator == "Equal to":
                return actual_value == expected_value
            elif operator == "Not equal to":
                return actual_value != expected_value
            elif operator == "Contains":
                return expected_value in actual_value
            elif operator == "Does not contain":
                return expected_value not in actual_value
            elif operator == "Starts with":
                return actual_value.startswith(expected_value)
            elif operator == "Ends with":
                return actual_value.endswith(expected_value)
            else:
                logger.warning(f"Unknown operator: {operator}")
                return False

        except Exception as e:
            logger.error(f"Error in condition check: {str(e)}")
            return False

    def _process_template(self, template: str, data: Dict[str, Any]) -> str:
        """Replace {{field}} placeholders with actual values from form data"""
        if not template:
            return ""
            
        result = template
        for key, value in data.items():
            placeholder = f"{{{{{key}}}}}"
            if placeholder in result:
                result = result.replace(placeholder, str(value))
        return result

    def _process_template(self, template: str, data: Dict[str, Any]) -> str:
        """Replace {{field}} placeholders with actual values from form data"""
        if not template:
            return ""
            
        result = template
        for key, value in data.items():
            placeholder = f"{{{{{key}}}}}"
            if placeholder in result:
                result = result.replace(placeholder, str(value))
        return result 

    async def _emit_event(self, event_type: str, source_node: Dict[str, Any], result: Any):
        logger.info(f"Emitting event '{event_type}' for node {source_node.get('id')}")
        for edge in self.workflow_edges:
            # Check if the edge is triggered by the event from the source node.
            if edge.get('source') == source_node.get('id') and edge.get('data', {}).get('triggerEvent') == event_type:
                target_node = next((n for n in self.workflow_nodes if n.get('id') == edge['target']), None)
                if target_node:
                    logger.info(f"Triggering node {target_node.get('id')} due to event '{event_type}'")
                    import asyncio
                    asyncio.create_task(self._execute_node_chain(target_node, self.workflow_edges, self.workflow_nodes, visited=set())) 