import io

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from google.adk.tools import ToolContext
from google.genai import types


async def render_chart(
    data: list[dict],
    chart_type: str,
    x_field: str,
    y_field: str,
    title: str,
    tool_context: ToolContext,
) -> dict:
    """Renderiza una gráfica PNG y la guarda como artifact de ADK.

    Args:
        data: filas (dicts) provenientes del sql_agent.
        chart_type: bar | line | pie | scatter.
        x_field: columna para el eje X (o etiquetas en pie).
        y_field: columna numérica para el eje Y (o valores en pie).
        title: título de la gráfica.
    """
    xs = [row.get(x_field) for row in data]
    ys = [row.get(y_field) for row in data]

    fig, ax = plt.subplots(figsize=(9, 5), dpi=120)
    if chart_type == "bar":
        ax.bar(range(len(xs)), ys)
        ax.set_xticks(range(len(xs)))
        ax.set_xticklabels([str(x) for x in xs], rotation=45, ha="right")
    elif chart_type == "line":
        ax.plot(range(len(xs)), ys, marker="o")
        ax.set_xticks(range(len(xs)))
        ax.set_xticklabels([str(x) for x in xs], rotation=45, ha="right")
    elif chart_type == "pie":
        ax.pie(ys, labels=[str(x) for x in xs], autopct="%1.1f%%")
    elif chart_type == "scatter":
        ax.scatter(xs, ys)
        ax.set_xlabel(x_field)
    else:
        plt.close(fig)
        return {"error": f"chart_type no soportado: {chart_type}"}

    if chart_type != "pie":
        ax.set_ylabel(y_field)
    ax.set_title(title)
    fig.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)

    filename = f"chart_{abs(hash(title)) % 10**8}.png"
    await tool_context.save_artifact(
        filename,
        types.Part.from_bytes(data=buf.getvalue(), mime_type="image/png"),
    )
    return {"artifact": filename, "rows_plotted": len(data)}
