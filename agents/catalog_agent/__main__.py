"""Servidor A2A del agente (Cloud Run, ingress interno).

Publica el AgentCard en /.well-known/agent-card.json y atiende JSON-RPC,
igual que los especialistas de bi-selfservice-agents. PUBLIC_URL debe
apuntar a la URL del servicio de Cloud Run.
"""
import os

import uvicorn
from google.adk.a2a.utils.agent_to_a2a import to_a2a

from .agent import root_agent

app = to_a2a(root_agent, port=int(os.environ.get("PORT", 8080)))

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
