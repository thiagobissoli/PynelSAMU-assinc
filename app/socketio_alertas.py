"""
WebSocket para alertas em tempo real.
Quando um alerta é alterado em qualquer tela, transmite para todas as telas do dashboard.
"""

from flask_socketio import SocketIO, join_room, leave_room

socketio = SocketIO(cors_allowed_origins="*", async_mode="threading")

ROOM_ALERTAS = "alertas"


def emit_alerta_atualizado(acao, alerta_dict=None, alerta_id=None):
    """
    Emite evento para todas as telas com painel de alertas.
    acao: 'resolvido' | 'criado' | 'arquivado'
    """
    try:
        socketio.emit(
            "alerta_atualizado",
            {"acao": acao, "alerta": alerta_dict, "alerta_id": alerta_id},
            room=ROOM_ALERTAS,
        )
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("Emit alerta: %s", e)


@socketio.on("connect")
def on_connect():
    pass


@socketio.on("join_alertas")
def on_join_alertas():
    """Cliente entra na sala de alertas (dashboard com painel de alertas)."""
    join_room(ROOM_ALERTAS)


@socketio.on("leave_alertas")
def on_leave_alertas():
    leave_room(ROOM_ALERTAS)


@socketio.on("disconnect")
def on_disconnect():
    pass
