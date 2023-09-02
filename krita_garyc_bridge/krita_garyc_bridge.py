import re
import xml.etree.ElementTree as ET
from functools import cache
from math import atan2, degrees, dist
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
VERSION = "0.1.4"


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


def create_document():
    """Creates document according to format this plugin expects."""

    document = APP.createDocument(800, 600, "sketch", "GRAYA", "U8", "", 72.0)
    document.setBackgroundColor(QColor("#FFFFFF"))
    APP.activeWindow().addView(document)  # make active, for setActiveNode to work
    root = document.rootNode()
    empty = root.childNodes()[0]  # default layer
    empty.remove()
    canvas = document.createVectorLayer("canvas")  # new layer
    root.addChildNode(canvas, None)
    return document


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


@cache
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
        d="M{"L".join(pairs)}" />"""
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
COMMAND_ARGC_P = {"M": 2, "L": 2, "V": 1, "H": 1, "Z": 0}
COMMAND_ARGV_P = re.compile(
    rf"({'|'.join(COMMAND_ARGC_P.keys())})|({FLOAT_P.pattern})", re.I | re.M
)
NAMESPACE_P = re.compile(r"{.+}(?P<tag>\w+)")


@cache
def svg_to_data(svg):
    if len(svg) == 0:
        return svg

    lines = []
    merge_distance = 1
    vector_root = ET.fromstring(svg)
    for obj in vector_root:
        tag = NAMESPACE_P.match(obj.tag).group("tag")
        if tag == "path":
            pen = [0, 0]
            new_lines = []
            line = []
            command = ""
            previous_command = ""
            args = []
            for match in COMMAND_ARGV_P.findall(obj.attrib["d"]):
                if command == "":
                    command = match[0]
                else:
                    args.append(float(match[1]))
                if COMMAND_ARGC_P[command.upper()] == len(args) and command != "":
                    if previous_command in ("M", "m") and command not in ("M", "m"):
                        line.append(pen)

                    if command == "M":
                        if len(line) != 0:
                            new_lines.append(line)
                            line = []
                        pen = args
                    elif command == "m":
                        if len(line) != 0:
                            new_lines.append(line)
                            line = []
                        pen = [pen[0] + args[0], pen[1] + args[1]]

                    elif command == "L":
                        pen = args
                        line.append(pen)
                    elif command == "l":
                        pen = [pen[0] + args[0], pen[1] + args[1]]
                        line.append(pen)

                    elif command == "H":
                        pen[0] = args[0]
                        line.append(pen)
                    elif command == "h":
                        pen[0] += args[0]
                        line.append(pen)

                    elif command == "V":
                        pen[1] = args[1]
                        line.append(pen)
                    elif command == "v":
                        pen[1] += args[1]
                        line.append(pen)

                    elif command in ("Z", "z"):
                        line.append(line[0])
                    else:
                        pass
                    # reset
                    previous_command = command
                    command = ""
                    args = []
            new_lines.append(line)

            # in rare case of line start being at (0, 0) there's no transform attribute
            if "transform" in obj.attrib:
                transform = obj.attrib["transform"]
                numbers = FLOAT_P.findall(transform)
                numbers = list(map(float, numbers))

                # krita does either translation or matrix
                # no skews, rotations or others
                if len(numbers) == 2:  # translation
                    for i, line in enumerate(new_lines):
                        for j, point in enumerate(line):
                            line[j] = [point[0] + numbers[0], point[1] + numbers[1]]
                        new_lines[i] = line
                elif len(numbers) == 6:  # matrix
                    for i, line in enumerate(new_lines):
                        for j, point in enumerate(line):
                            line[j] = [
                                numbers[0] * point[0]
                                + numbers[2] * point[1]
                                + numbers[4],
                                numbers[1] * point[0]
                                + numbers[3] * point[1]
                                + numbers[5],
                            ]
                        new_lines[i] = line

            # throw out of bounds, merge, round, flatten
            for line in new_lines:
                previous_point = []
                flattened_line = []
                for point in line:
                    point = list(map(round, point))
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
                        if (  # skip if smaller than merge distance
                            abs(previous_point[0] - point[0]) >= merge_distance
                            or abs(previous_point[1] - point[1]) >= merge_distance
                        ):
                            flattened_line += [
                                ENCODER[point[0]],
                                ENCODER[point[1]],
                            ]
                    previous_point = point
                lines.append("".join(flattened_line))
        else:
            continue
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

    if len(data) == 0:
        show_error("You don't have any vector layers or vector layers are empty!")

    return data


# home-made shitty optimization
@cache
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


CLIPBOARD = krita.QtGui.QGuiApplication.clipboard()


def read_clipboard():
    """Reads and returns text from clipboard as a string."""
    return CLIPBOARD.text()


def write_clipboard(text):
    """Writes text to clipboard."""
    if len(text) != 0:
        CLIPBOARD.setText(text)


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


# +-----------------------+
# |Create sketch file     |create_document
# |Import data as layer   |read_clipboard -> data_to_layer
# |Copy document as data  |document_to_data -> write_clipboard
# |Post to sketch         |document_to_data -> post_data
# +-----------------------+
class KritaGarycBridge(krita.DockWidget):  # pylint: disable=too-few-public-methods
    """Plugin's docker. Contains buttons so the user can use the plugin."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{NAME} v{VERSION}")
        layout = QVBoxLayout()

        def make_button(icon, label, tooltip, method):
            button = QPushButton(APP.icon(icon), label)
            button.setToolTip(tooltip)
            button.clicked.connect(method)
            return button

        buttons = [
            [
                "document-new",
                "Create blank sketch file",
                create_document.__doc__,
                create_document,
            ],
            [
                "document-import",
                "Import clipboard as layer",
                "Import sketch data from clipboard into a new layer.",
                lambda: data_to_layer(read_clipboard()),
            ],
            [
                "document-export",
                "Export document to clipboard",
                "Export vector data from all layers to clipboard in sketch data format.",
                lambda: write_clipboard(document_to_data()),
            ],
            [
                "reload-preset",
                "Generate optimized layer",
                "Runs ink optimizer on doucment and returns .",
                lambda: write_clipboard(optimize(document_to_data())),
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
