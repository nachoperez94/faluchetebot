import os
import re
import logging
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from woocommerce import API

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
WC_URL         = os.environ["WC_URL"]
WC_KEY         = os.environ["WC_CONSUMER_KEY"]
WC_SECRET      = os.environ["WC_CONSUMER_SECRET"]

wcapi = API(url=WC_URL, consumer_key=WC_KEY, consumer_secret=WC_SECRET, version="wc/v3", timeout=30)

ESTADOS_VALIDOS = {"processing", "completed", "on-hold"}

MESES = {
    "enero":1,"febrero":2,"marzo":3,"abril":4,"mayo":5,"junio":6,
    "julio":7,"agosto":8,"septiembre":9,"octubre":10,"noviembre":11,"diciembre":12
}

def extraer_fecha(nombre):
    nombre_l = nombre.lower()
    m = re.search(r'(\d{1,2})\s+de\s+(\w+)', nombre_l)
    if m:
        dia = int(m.group(1))
        mes = MESES.get(m.group(2))
        if mes:
            anio = datetime.now().year
            try:
                fecha = datetime(anio, mes, dia)
                if fecha < datetime.now() - timedelta(days=30):
                    fecha = datetime(anio + 1, mes, dia)
                return fecha
            except ValueError:
                pass
    return None

def semana_actual():
    hoy = datetime.now()
    lunes = hoy - timedelta(days=hoy.weekday())
    domingo = lunes + timedelta(days=6)
    return lunes.replace(hour=0,minute=0,second=0), domingo.replace(hour=23,minute=59,second=59)

def obtener_cursos_semana():
    lunes, domingo = semana_actual()
    cursos = {}
    fecha_desde = (datetime.utcnow() - timedelta(days=90)).strftime("%Y-%m-%dT%H:%M:%S")
    page = 1

    while True:
        pedidos = wcapi.get("orders", params={
            "status": ",".join(ESTADOS_VALIDOS),
            "after": fecha_desde,
            "per_page": 100,
            "page": page
        }).json()

        if not pedidos:
            break

        for pedido in pedidos:
            billing  = pedido.get("billing", {})
            nombre   = billing.get("first_name", "").strip()
            apellido = billing.get("last_name", "").strip()
            telefono = billing.get("phone", "").strip()

            for item in pedido.get("line_items", []):
                pid         = item.get("product_id")
                nombre_prod = item.get("name", "")
                cantidad    = item.get("quantity", 1)
                fecha_prod  = extraer_fecha(nombre_prod)

                if fecha_prod and lunes <= fecha_prod <= domingo:
                    if pid not in cursos:
                        cursos[pid] = {"nombre": nombre_prod, "fecha": fecha_prod, "alumnos": [], "total_plazas": 0}

                    if cantidad > 1:
                        entrada = f"{nombre} {apellido} | {telefono} | {cantidad} plazas"
                    else:
                        entrada = f"{nombre} {apellido} | {telefono}"

                    cursos[pid]["alumnos"].append(entrada)
                    cursos[pid]["total_plazas"] += cantidad

        if len(pedidos) < 100:
            break
        page += 1

    # Ordenar por fecha del curso (mas proximos primero)
    cursos_ordenados = sorted(cursos.values(), key=lambda x: x["fecha"])
    return cursos_ordenados, lunes, domingo

async def cmd_semana(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Consultando cursos de esta semana...")
    try:
        cursos, lunes, domingo = obtener_cursos_semana()
    except Exception as e:
        logger.error(f"Error: {e}")
        await update.message.reply_text(f"Error al conectar con la web: {e}")
        return

    if not cursos:
        await update.message.reply_text(
            f"No hay cursos esta semana ({lunes.strftime('%d/%m')} - {domingo.strftime('%d/%m')})."
        )
        return

    for datos in cursos:
        n_pedidos = len(datos["alumnos"])
        n_plazas  = datos["total_plazas"]
        dia_semana = datos["fecha"].strftime("%A %d/%m").capitalize()

        lineas = [
            f"CURSO: {datos['nombre']}",
            f"{dia_semana}",
            f"Pedidos: {n_pedidos} | Plazas totales: {n_plazas}",
            ""
        ]
        for a in datos["alumnos"]:
            lineas.append(f"  - {a}")

        texto = "\n".join(lineas)
        for i in range(0, len(texto), 4000):
            await update.message.reply_text(texto[i:i+4000])

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Hola! Soy el bot de inscripciones de la Escuela FREMOCV.\n\n"
        "/semana - Cursos de esta semana con listado de alumnos y plazas"
    )

def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start",  cmd_start))
    app.add_handler(CommandHandler("semana", cmd_semana))
    logger.info("Bot arrancado. Esperando comandos...")
    app.run_polling()

if __name__ == "__main__":
    main()
