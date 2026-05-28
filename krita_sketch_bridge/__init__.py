try:
    import krita
except ImportError:
    import PyKrita as krita

from .krita_sketch_bridge import KritaSketchBridge

DOCKER_ID = "krita_sketch_bridge"
app = krita.Krita.instance()
dock_widget_factory = krita.DockWidgetFactory(
    DOCKER_ID, krita.DockWidgetFactoryBase.DockRight, KritaSketchBridge
)

app.addDockWidgetFactory(dock_widget_factory)
