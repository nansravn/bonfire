"""Azure Functions entry points: thin wrappers over bonfire.function (spec section 6)."""
import json
import logging
import os
from datetime import datetime, timezone

import azure.functions as func

from bonfire.function.interactions import handle_http

app = func.FunctionApp()
_clients = None


def clients():
    """Real clients, built once per worker process."""
    global _clients
    if _clients is None:
        from azure.identity import DefaultAzureCredential

        from bonfire.core.clock import Clock
        from bonfire.core.compute import AzureCompute
        from bonfire.core.config import load_config
        from bonfire.core.discord import HttpReplies, HttpWebhook
        from bonfire.core.events import CosmosEventSink
        from bonfire.core.state import AzureStateTable
        from bonfire.function.worker import Clients

        config = load_config(os.environ)
        credential = DefaultAzureCredential()
        _clients = Clients(
            config=config,
            clock=Clock(),
            state=AzureStateTable(config.state_table_endpoint, credential),
            events=CosmosEventSink(config.events_endpoint, credential),
            compute=AzureCompute(config.vm_resource_id, credential),
            webhook=HttpWebhook(os.environ["DISCORD_WEBHOOK_URL"]),
            replies=HttpReplies(os.environ["DISCORD_APPLICATION_ID"]),
        )
    return _clients


@app.function_name("interactions")
@app.route(route="interactions", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
@app.queue_output(arg_name="outq", queue_name="interactions", connection="AzureWebJobsStorage")
def interactions(req: func.HttpRequest, outq: func.Out[str]) -> func.HttpResponse:
    result = handle_http(dict(req.headers), req.get_body(), os.environ["DISCORD_PUBLIC_KEY"],
                         datetime.now(timezone.utc))
    if result.queue_message:
        outq.set(result.queue_message)
    body = json.dumps(result.body) if result.body is not None else ""
    return func.HttpResponse(body, status_code=result.status, mimetype="application/json")


@app.function_name("worker")
@app.queue_trigger(arg_name="msg", queue_name="interactions", connection="AzureWebJobsStorage")
def worker(msg: func.QueueMessage) -> None:
    from bonfire.function.worker import handle_interaction

    handle_interaction(json.loads(msg.get_body().decode()), clients())


@app.function_name("watchdog")
@app.timer_trigger(arg_name="timer", schedule="0 */15 * * * *", run_on_startup=False, use_monitor=True)
def watchdog(timer: func.TimerRequest) -> None:
    from bonfire.function.watchdog import run_watchdog

    logging.getLogger("bonfire.watchdog").info("tick")
    run_watchdog(clients())
