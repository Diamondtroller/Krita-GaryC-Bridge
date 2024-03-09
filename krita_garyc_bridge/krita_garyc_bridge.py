import re
import xml.etree.ElementTree as ET
from math import atan2, cos, degrees, dist, pi, sin
from urllib.request import Request, urlopen

try:
    import krita
except ImportError:
    import PyKrita as krita  # generated autocomplete

from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (
    QErrorMessage,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

NAME = "Krita GaryC Bridge"
VERSION = "0.1.5"


def generate_base36():
    """Hacky base 36 encoder/decoder generator, works only below 36**2"""

    def digit(digit):
        if digit < 10:
            return str(digit)
        return chr(digit + 87)

    single_digits = [(i, digit(i)) for i in range(36)]
    encoder = [None] * 36 * 36
    decoder = {}
    for i, first in single_digits:
        wholes = 36 * i
        for j, second in single_digits:
            b36 = first + second
            encoder[wholes + j] = b36
            decoder[b36] = wholes + j
    return encoder, decoder


ENCODER, DECODER = generate_base36()


def show_error(message):
    """Helper function to show an error to user."""

    error = QErrorMessage()
    error.setWindowTitle(NAME)
    error.showMessage(message)
    error.exec()


def show_message(message):
    """Helper function to show a message to user."""

    message_box = QMessageBox()
    message_box.setWindowTitle(NAME)
    message_box.setText(message)
    message_box.exec()


APP = krita.Krita.instance()


def start_sketch():
    """Creates a document file  according to format this plugin expects."""

    document = APP.createDocument(800, 600, "sketch", "RGBA", "U8", "", 72.0)
    document.setBackgroundColor(QColor("#FFFFFF"))
    APP.activeWindow().addView(document)  # make active, for setActiveNode to work
    root = document.rootNode()
    empty = root.childNodes()[0]  # default layer
    empty.remove()
    canvas = document.createVectorLayer("canvas")  # new layer
    root.addChildNode(canvas, None)
    return document


def load_tool_options():
    """Loads the correct tool settings to make the sketches look like sketches."""
    view = APP.activeWindow().activeView()
    view.setBrushSize(3)
    view.setForeGroundColor(
        krita.ManagedColor.fromQColor(QColor("#000000"), view.canvas())
    )
    for action in ["KisToolPencil", "view_snap_to_pixel"]:
        APP.action(action).trigger()


def get_document():
    """Used to retrieve document and throw error if there's none."""

    document = APP.activeDocument()
    if document is None:
        show_error(
            """You haven't opened any krita file to post.
             Creating a new document according to garyc.me/sketch format."""
        )
    return document


SPLITTER_P = re.compile(r"[a-z\d]{4}")
FILTER_P = re.compile(r"[^a-z\d ]")


def data_to_svg(data):
    svg = "<svg>"
    for base36_line in data.split():
        pairs = SPLITTER_P.findall(base36_line)
        for i, pos in enumerate(pairs):
            pairs[i] = f"{DECODER[pos[0:2]]} {DECODER[pos[2:4]]}"
        svg += f"""<path fill="none"
        stroke="#000000"
        stroke-width="3"
        stroke-linejoin="round"
        d="M{"L".join(pairs)}"/>"""
    svg += "</svg>"
    return svg


def data_to_layer(data):
    """Imports sketch data as vector layer into document."""

    document = get_document()
    if document is None:
        return

    if FILTER_P.search(data) is not None:
        show_error("Your clipboard has non-sketch data. Can't import it.")
        return

    imported_layer = document.createVectorLayer("Imported sketch")

    imported_layer.addShapesFromSvg(data_to_svg(data))
    root_node = document.rootNode()
    root_node.addChildNode(imported_layer, root_node.childNodes()[0])


FLOAT_P = re.compile(r"[-+]?\d+\.?\d*(?:e[-+]?\d+)?")
COMMAND_ARGC = {"C": 6, "M": 2, "L": 2, "V": 1, "H": 1, "Z": 0}
COMMAND_ARGV_P = re.compile(
    rf"({'|'.join(COMMAND_ARGC.keys())})|({FLOAT_P.pattern})", re.I | re.M
)
NAMESPACE_P = re.compile(r"{.+}(?P<tag>\w+)")


def compile_path(attributes):
    pen = [0, 0]
    line = []
    subline = []
    command = ""
    previous_command = ""
    args = []
    # parses token, by token
    for match in COMMAND_ARGV_P.findall(attributes["d"]):
        if command == "":
            command = match[0]
        else:
            args.append(float(match[1]))

        if COMMAND_ARGC[command.upper()] == len(args) and command != "":
            if command.islower():
                for i, _ in enumerate(args):
                    args[i] += pen[i % 2]
                command = command.upper()

            if previous_command == "M" and command != "M":
                subline.append(pen)

            if command == "C":
                quotients = [1, 3, 3, 1]

                args = pen + args
                for time in range(1001):
                    t = time / 1000
                    at = 1 - t
                    pen = [0, 0]
                    for i in range(4):
                        factor = quotients[i] * at ** (3 - i) * t**i
                        pen[0] += factor * args[2 * i]
                        pen[1] += factor * args[2 * i + 1]

                    subline.append(pen)
                pen = args[-2:]
            elif command == "M":
                if len(subline) != 0:
                    line.append(subline)
                    subline = []
                pen = args
            elif command == "L":
                pen = args
                subline.append(pen)
            elif command == "H":
                pen[0] = args[0]
                subline.append(pen)
            elif command == "V":
                pen[1] = args[1]
                subline.append(pen)
            elif command == "Z":
                subline.append(subline[0])
            # reset
            previous_command = command
            command = ""
            args = []

    if len(subline) >= 2:
        line.append(subline)
    return line


def compile_rect(attributes):
    width = float(attributes["width"])
    height = float(attributes["height"])
    return [[[0, 0], [width, 0], [width, height], [0, height], [0, 0]]]


def compile_ellipse(attributes):
    center_x = float(attributes["cx"])
    center_y = float(attributes["cy"])
    if "r" in attributes:
        radius_x = float(attributes["r"])
        radius_y = radius_x
    else:
        radius_x = float(attributes["rx"])
        radius_y = float(attributes["ry"])

    steps = max(round(max(radius_x, radius_y) / 6 * pi), 6)
    new_lines = [None] * (steps + 1)
    for step in range(0, steps, 1):
        rad = step / steps * 2 * pi
        new_lines[step] = [
            center_x - radius_x * cos(rad),
            center_y + radius_y * sin(rad),
        ]
    new_lines[-1] = new_lines[0]  # connect ends
    return [new_lines]


MERGE_DISTANCE = 1


def svg_to_data(svg):
    if len(svg) == 0:
        return svg

    lines = []
    # grid_refuse = 0.15
    vector_root = ET.fromstring(svg)

    compile_map = {
        "path": compile_path,
        "rect": compile_rect,
        "circle": compile_ellipse,
        "ellipse": compile_ellipse,
    }

    for obj in vector_root:
        tag = NAMESPACE_P.match(obj.tag).group("tag")
        if tag in compile_map:
            new_lines = compile_map[tag](obj.attrib)
        else:
            continue

        if "transform" in obj.attrib:
            transform = obj.attrib["transform"]
            numbers = list(map(float, FLOAT_P.findall(transform)))

            # krita does either translation or matrix
            # don't have to handle skews, rotations or others
            if len(numbers) == 2:  # translation
                for i, line in enumerate(new_lines):
                    for j, point in enumerate(line):
                        line[j] = [
                            round(point[0] + numbers[0]),
                            round(point[1] + numbers[1]),
                        ]
                    new_lines[i] = line
            elif len(numbers) == 6:  # matrix
                for i, line in enumerate(new_lines):
                    for j, point in enumerate(line):
                        line[j] = [
                            round(
                                numbers[0] * point[0]
                                + numbers[2] * point[1]
                                + numbers[4]
                            ),
                            round(
                                numbers[1] * point[0]
                                + numbers[3] * point[1]
                                + numbers[5]
                            ),
                        ]
                    new_lines[i] = line
        else:  # sometimes there's no transform
            for i, line in enumerate(new_lines):
                for j, point in enumerate(line):
                    line[j] = [round(point[0]), round(point[1])]
                new_lines[i] = line

        # throw out of bounds, merge, round, flatten
        for line in new_lines:
            previous_point = []
            flattened_line = []
            for point in line:
                # point_err = [point[0] % 1, point[1] % 1]
                # if (
                #     point_err[0] > (0.5 - grid_refuse)
                #     and point_err[0] < (0.5 + grid_refuse)
                # ) or (
                #     point_err[1] > (0.5 - grid_refuse)
                #     and point_err[1] < (0.5 + grid_refuse)
                # ):
                #     continue

                # point = list(map(round, point))
                if not isinstance(point[0], int):
                    break
                # out of bounds
                if point[0] > 800 or point[0] < 0 or point[1] > 600 or point[1] < 0:
                    i += 1
                    continue
                if not previous_point:
                    flattened_line += [
                        ENCODER[point[0]],
                        ENCODER[point[1]],
                    ]
                else:
                    if (  # throw out unnecessary points
                        abs(previous_point[0] - point[0]) >= MERGE_DISTANCE
                        or abs(previous_point[1] - point[1]) >= MERGE_DISTANCE
                    ):
                        flattened_line += [
                            ENCODER[point[0]],
                            ENCODER[point[1]],
                        ]
                previous_point = point
            lines.append("".join(flattened_line))
    return " ".join(lines)


def document_to_data():
    """Exports vector data from all document's layers to sketch data and returns it as string."""

    document = get_document()
    if document is None:
        return ""

    layers = document.rootNode().childNodes()
    data = ""
    for layer in layers:
        if layer.visible() and str(layer.type()) == "vectorlayer":
            data += svg_to_data(layer.toSvg())

    if len(data) < 4:
        show_error("You don't have any vector layers or vector layers are empty!")

    return data


# home-made shitty optimization
def optimize(data):
    new_data = []
    for base36_line in data.split():
        points = SPLITTER_P.findall(base36_line)
        points_len = len(points)
        if points_len == 2:
            new_data.append(base36_line)
            continue
        start = 0
        end = start + 2
        new_line = points[0]  # pre-adding
        while start + 1 < points_len:
            point_0_str = points[start]
            point_0 = (DECODER[point_0_str[0:2]], DECODER[point_0_str[2:4]])

            while end < points_len:
                point_1_str = points[end - 1]
                point_1 = (DECODER[point_1_str[0:2]], DECODER[point_1_str[2:4]])

                point_2_str = points[end]
                point_2 = (DECODER[point_2_str[0:2]], DECODER[point_2_str[2:4]])

                ddeg = degrees(
                    abs(
                        atan2(-point_2[1] + point_1[1], point_2[0] - point_1[0])
                        - atan2(-point_1[1] + point_0[1], point_1[0] - point_0[0])
                    )
                    ** 0.5
                )
                ddist = dist(point_0, point_1) + dist(point_1, point_2)
                val = ddeg * ddist
                if val > 230:  # this threshold was determined experimentally
                    new_line += point_1_str
                    break  # go to next starting point
                end += 1
            start = end - 1
            end = start + 2
        new_line += points[-1]  # post-adding
        new_data.append(new_line)
    return " ".join(new_data)


class Clipboard:
    """Wrapper of Krita's clipboard"""

    def __init__(self, source):
        self.source = source

    def read(self):
        """Reads and returns text from clipboard as a string."""
        return self.source.text()

    def write(self, text):
        """Writes text if it's not empty."""
        if len(text) != 0:
            self.source.setText(text)


ESCAPED_NAME = NAME.replace(" ", "-")
request = Request(
    "https://garyc.me/sketch/swap.php?v=32",
    headers={
        "Accept": "text/plain",
        "Origin": f"https://{ESCAPED_NAME}",
        "User-Agent": f"{ESCAPED_NAME}/{VERSION} (+https://github.com/Diamondtroller)",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "cross-site",
        "Host": "garyc.me",
    },
    method="POST",
)


def post_data(data):
    """Sends HTTP POST request to https://garyc.me/sketch to post a sketch"""

    data_len = len(data)
    if data_len == 0:
        return  # Related error already thrown in document_to_data()
    if data_len <= 2 * 50:
        show_error(
            "There's no or almost none data to post. Please draw something before swapping."
        )
        return

    request.data = data.encode("ascii")
    with urlopen(request) as response:
        sketch_id = response.read()

    if sketch_id == b"":
        show_error("There was an error posting sketch.")
        return

    sketch_id = int(sketch_id) - 1

    def make_link(link):
        ref = f"https://{link}/sketch/gallery.php#{sketch_id}"
        return f'<a href="{ref}">{ref}</a>'

    show_message(
        f"""
        <p>Your sketch has been posted! Here's the link to your sketch:</p>
        <br>
        {make_link('garyc.me')}
        <br>
        {make_link('noz.rip')}
        """
    )


class KritaGarycBridge(krita.DockWidget):  # pylint: disable=too-few-public-methods
    """Plugin's docker. Contains buttons so the user can use the plugin."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{NAME} v{VERSION}")
        layout = QVBoxLayout()
        clipboard = Clipboard(krita.QtGui.QGuiApplication.clipboard())

        def make_button(icon, label, tooltip, method):
            button = QPushButton(APP.icon(icon), label)
            button.setToolTip(tooltip)
            button.clicked.connect(method)
            return button

        buttons = [
            [
                "document-new",
                "Create sketch file",
                start_sketch.__doc__,
                start_sketch,
            ],
            [
                "draw-freehand",
                "Load tool options",
                load_tool_options.__doc__,
                load_tool_options,
            ],
            [
                "import-as-paintLayer",
                "Import clipboard as layer",
                "Import sketch data from clipboard into a new layer.",
                lambda: data_to_layer(clipboard.read()),
            ],
            [
                "document-export",
                "Export document to clipboard",
                "Export vector data from all layers to clipboard in sketch data format.",
                lambda: clipboard.write(document_to_data()),
            ],
            [
                "reload-preset",
                "Generate optimized document",
                "Runs ink optimizer on document and save it into clipboard.",
                lambda: clipboard.write(optimize(document_to_data())),
            ],
            [
                "document-save",
                "Post to sketch",
                "Post the document to https://garyc.me/sketch.",
                lambda: post_data(document_to_data()),
            ],
        ]

        for button in buttons:
            layout.addWidget(make_button(*button))

        docker = QWidget()
        docker.setLayout(layout)
        self.setWidget(docker)

    def canvasChanged(self, canvas):  # pylint: disable=invalid-name
        """Required to override."""
