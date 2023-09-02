try:
    import krita
except ImportError:
    import PyKrita as krita

from .krita_garyc_bridge import KritaGarycBridge

DOCKER_ID = "krita_garyc_bridge"
app = krita.Krita.instance()
dock_widget_factory = krita.DockWidgetFactory(
    DOCKER_ID, krita.DockWidgetFactoryBase.DockRight, KritaGarycBridge
)

app.addDockWidgetFactory(dock_widget_factory)
