# src/ai/environment_generator.py
"""
AI-Powered Environment Generator using Composio SDK
Generates infrastructure configurations from natural language descriptions
"""
import openai
import json
import logging
from typing import Dict, Any, Optional
from datetime import datetime

try:
    from composio import Composio
    from composio_openai import OpenAIProvider
    COMPOSIO_AVAILABLE = True
except ImportError:
    Composio = None
    OpenAIProvider = None
    COMPOSIO_AVAILABLE = False

logger = logging.getLogger(__name__)


class EnvironmentGenerator:
    """Generate environment configs from natural language using Composio tools"""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key
        self.client = None
        self.composio = None
        self.max_iterations = 5
        self._initialize_clients()
    
    def _initialize_clients(self):
        try:
            if openai:
                self.client = openai.OpenAI(api_key=self.api_key)
            
            if COMPOSIO_AVAILABLE and Composio and OpenAIProvider:
                try:
                    self.composio = Composio(provider=OpenAIProvider())
                except Exception as e:
                    logger.warning(f"Composio not available: {e}")
        except Exception as e:
            logger.error(f"Failed to initialize clients: {e}")
            raise
    
    def generate(
        self,
        user_id: str,
        description: str,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Generate docker-compose and devcontainer.json from description"""
        session = None
        tools = []
        
        if self.composio:
            try:
                session = self.composio.create(user_id=user_id)
                tools = session.tools()
            except Exception as e:
                logger.warning(f"Failed to create Composio session: {e}")
        
        context_str = ""
        pr_number = None
        repo_name = "app"
        if context:
            context_str = f"\nContext:\n{json.dumps(context, indent=2)}"
            pr_number = context.get('pr_number')
            repo_name = context.get('repo_name', 'app')
        
        db_name = f"db-preview-pr{pr_number}-{repo_name}" if pr_number else f"db-{repo_name}"
        
        system_prompt = f"""You are an expert DevOps engineer specializing in container infrastructure.
Your task is to generate complete, production-ready environment configurations from natural language descriptions.

Database Naming Convention: {db_name}
Network Isolation: Ensure all services are in an isolated 'disposable-net' network.

You have access to tools that can inspect repositories, check dependencies, and validate configs.

Generate THREE outputs:
1. A complete docker-compose.yml with all necessary services
2. A devcontainer.json for VS Code integration  
3. A brief explanation of your design choices

Requirements:
- Use modern best practices
- Include health checks where appropriate
- Set reasonable resource limits
- Follow security best practices (non-root users, read-only filesystems where possible)
- Make it production-ready

Respond in JSON format with keys: docker_compose, devcontainer, explanation"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Generate config for: {description}\n{context_str}"}
        ]
        
        for iteration in range(self.max_iterations):
            try:
                response = self.client.chat.completions.create(
                    model="gpt-4-turbo-preview",
                    messages=messages,
                    tools=tools if tools else None,
                    tool_choice="auto" if tools else None,
                    response_format={"type": "json_object"} if not tools else None
                )
                
                assistant_message = response.choices[0].message
                
                if assistant_message.tool_calls:
                    messages.append(assistant_message)
                    for tool_call in assistant_message.tool_calls:
                        tool_result = self._execute_tool_call(session, tool_call)
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": json.dumps(tool_result)
                        })
                    continue
                
                result = json.loads(assistant_message.content)
                result['metadata'] = {
                    'generated_at': datetime.utcnow().isoformat(),
                    'iterations': iteration + 1
                }
                return result
                    
            except Exception as e:
                logger.error(f"Generation failed: {e}")
                if iteration == self.max_iterations - 1:
                    return self._generate_fallback(description)
        
        return self._generate_fallback(description)
    
    def _execute_tool_call(self, session: Any, tool_call: Any) -> Dict[str, Any]:
        if not session:
            return {'error': 'No session'}
        try:
            return session.execute_tool_call(tool_call)
        except Exception as e:
            return {'error': str(e)}
    
    def _generate_fallback(self, description: str) -> Dict[str, Any]:
        return {
            'docker_compose': 'version: "3.8"\nservices:\n  app:\n    image: alpine\n    command: sleep infinity',
            'devcontainer': '{}',
            'explanation': 'Fallback generated due to error',
            'error': True
        }


def get_environment_generator(api_key: Optional[str] = None) -> EnvironmentGenerator:
    global _generator
    if _generator is None:
        _generator = EnvironmentGenerator(api_key)
    return _generator

_generator = None
