"""Viz Agent: gráficas a partir de resultados YA autorizados.

Regla heredada del repo hermano: las imágenes viajan como artifacts del ADK
(`tool_context.save_artifact`), nunca como bytes dentro del texto del modelo.

Frontera de datos: este agente recibe del sql_agent únicamente el resultado
tabular que BigQuery ya filtró/enmascaró para el usuario. No tiene tools de
consulta propias: no puede ampliar el alcance de datos por su cuenta.
"""

from google.adk.agents import Agent

from ..common.model_factory import get_model
from .tools import render_chart

root_agent = Agent(
    name="viz_agent",
    model=get_model("viz"),
    description=(
        "Renderiza gráficas (barras, líneas, pie, scatter) como PNG inline "
        "a partir de datos tabulares ya autorizados por BigQuery."
    ),
    instruction="""
Eres el agente de visualización.

1. Recibes datos tabulares (lista de dicts) del orquestador. NO consultas
   datos por tu cuenta; si faltan datos, pídelos al orquestador.
2. Elige el tipo de gráfica según la forma de los datos: serie temporal ->
   líneas; categorías vs medida -> barras; proporciones (<=6 categorías) ->
   pie; dos medidas continuas -> scatter.
3. Llama `render_chart` y devuelve un resumen de 1-2 frases de lo que la
   gráfica muestra. El PNG viaja como artifact; nunca describas los bytes.
4. Máximo ~30 categorías en un chart; si hay más, agrega "otros" o sugiere
   top-N.
""",
    tools=[render_chart],
)
