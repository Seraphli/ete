import colorsys
import random
import re
import types 

from PyQt4.QtGui import QGraphicsItem,QGraphicsRectItem, QColor, QPen, QBrush
from PyQt4 import QtCore

_LINE_TYPE_CHECKER = lambda x: x in (0,1,2)
_SIZE_CHECKER = lambda x: isinstance(x, int)
_COLOR_MATCH = re.compile("^#[A-Fa-f\d]{6}$")
_COLOR_CHECKER = lambda x: re.match(_COLOR_MATCH, x)
_NODE_TYPE_CHECKER = lambda x: x in ["sphere", "circle", "square"]
_BOOL_CHECKER =  lambda x: isinstance(x, bool) or x in (0,1)

FACE_POSITIONS = set(["branch-right", "branch-top", "branch-bottom", "float", "aligned"])

__all__  = ["NodeStyle", "TreeStyle", "FaceContainer", "_leaf", "add_face_to_node"]

NODE_STYLE_DEFAULT = [
    ["fgcolor",          "#0030c1",    _COLOR_CHECKER                           ],
    ["bgcolor",          "#FFFFFF",    _COLOR_CHECKER                           ],
    ["node_bgcolor",     "#FFFFFF",    _COLOR_CHECKER                           ],
    ["partition_bgcolor","#FFFFFF",    _COLOR_CHECKER                           ],
    ["faces_bgcolor",    "#FFFFFF",    _COLOR_CHECKER                           ],    
    ["vt_line_color",    "#000000",    _COLOR_CHECKER                           ],
    ["hz_line_color",    "#000000",    _COLOR_CHECKER                           ],
    ["hz_line_type",     0,            _LINE_TYPE_CHECKER                       ], # 0 solid, 1 dashed, 2 dotted
    ["vt_line_type",     0,            _LINE_TYPE_CHECKER                       ], # 0 solid, 1 dashed, 2 dotted
    ["size",             3,            _SIZE_CHECKER                            ], # node circle size 
    ["shape",            "circle",     _NODE_TYPE_CHECKER                       ], 
    ["draw_descendants", True,         _BOOL_CHECKER                            ],
    ["hz_line_width",          1,      _SIZE_CHECKER                            ],
    ["vt_line_width",          1,      _SIZE_CHECKER                            ]
    ]


# _faces and faces are registered to allow deepcopy to work on nodes
VALID_NODE_STYLE_KEYS = set([i[0] for i in NODE_STYLE_DEFAULT]) | set(["_faces", "faces"])

class _Border(object):
    def __init__(self):
        self.width = 0
        self.line_style = 0
        self.color = None 

    def apply(self, item):
        if self.width:
            r = item.boundingRect()
            border = QGraphicsRectItem(r)
            border.setParentItem(item)
            pen = QPen()
            set_pen_style(pen, self.line_style)
            pen.setWidth(self.width)
            pen.setCapStyle(QtCore.Qt.FlatCap)
            pen.setColor(QColor(self.color))
            border.setPen(pen)
            return border
        else:
            return None

class _Background(object):
    def __init__(self):
        self.color = None

    def apply(self, item):
        if self.color: 
            r = item.boundingRect()
            bg = QGraphicsRectItem(r)
            bg.setParentItem(item)
            pen = QPen(QColor(self.color))
            brush = QBrush(QColor(self.color))
            bg.setPen(pen)
            bg.setBrush(brush)
            bg.setFlag(QGraphicsItem.ItemStacksBehindParent)
            return bg
        else:
            return None
        


class _ActionDelegator(object):
    """ Used to associate GUI Functions to nodes and faces """ 

    def get_delegate(self):
        return self._delegate

    def set_delegate(self, delegate):
        if hasattr(delegate, "init"):
            delegate.init(self)

        for attr in dir(delegate):
            if not attr.startswith("_") and attr != "init" :
                fn = getattr(delegate, attr)
                setattr(self, attr, types.MethodType(fn, self))
        self._delegate = delegate

    delegate = property(get_delegate, set_delegate)

    def __init__(self):
        self._delegate = None
      
class NodeStyle(dict):
    """ A dictionary with all valid node graphical attributes.  

    :argument #0030c1 fgcolor: RGB code or SVG color name
    :argument #FFFFFF bgcolor: RGB code or SVG color name
    :argument #FFFFFF node_bgcolor: RGB code or SVG color name
    :argument #FFFFFF partition_bgcolor: RGB code or SVG color name
    :argument #FFFFFF faces_bgcolor: RGB code or SVG color name
    :argument #000000 vt_line_color: RGB code or SVG color name
    :argument #000000 hz_line_color: RGB code or SVG color name
    :argument 0 hz_line_type: integer number
    :argument 0 vt_line_type: integer number
    :argument 3 size: integer number
    :argument "circle" shape: "circle", "square" or "sphere"
    :argument True draw_descendants: Mark an internal node as a leaf. 
    :argument 1 hz_line_width: integer number 
    :argument 1 vt_line_width: integer number
    
    """

    def __init__(self, *args, **kargs):

        super(NodeStyle, self).__init__(*args, **kargs)
        super(NodeStyle, self).__setitem__("faces", {})
        self.init()
        self._block_adding_faces = False

    def init(self):
        for key, dvalue, checker in NODE_STYLE_DEFAULT:
            if key not in self:
                self[key] = dvalue
            elif not checker(self[key]):
                raise ValueError("'%s' attribute in node style has not a valid value: %s" %\
                                     (key, self[key]))
        super(NodeStyle, self).__setitem__("_faces", {})
        # copy fixed faces to the faces dict that will be drawn 
        for pos, values in self["faces"].iteritems():
            for col, faces in values.iteritems():
                self["_faces"].setdefault(pos, {})
                self["_faces"][pos][col] = list(faces)

    def add_fixed_face(self, face, position, column):
        if self._block_adding_faces:
            raise AttributeError("fixed faces cannot be modified while drawing.")
            
        """ 
        Add faces as a fixed feature of this node style. This faces
        are always rendered.

        face: a Face compatible instance
        Valid positions: %s
        column: an integer number defining face relative position
         """ %FACE_POSITIONS
        self["faces"].setdefault(position, {})
        self["faces"][position].setdefault(int(column), []).append(face)

    def __setitem__(self, i, y):
        if i not in VALID_NODE_STYLE_KEYS:
            raise ValueError("'%s' is not a valid key for NodeStyle instances" %i)
        super(NodeStyle, self).__setitem__(i, y)

    def clear(self):
        super(NodeStyle, self).__setitem__("_faces", {})

class TreeStyle(object):
    """ 
    Contains all the general image properties used to render a tree

    **TREE SHAPE AND IMAGE DESIGN**
        
    :var "rect" mode: Valid modes are "c" (circular) or "r"
      (rectangular).

    :var None layout_fn: Layout function used to dynamically control
      the aspect of nodes. Valid values are: None or a pointer to a method,
      function, etc.
                   
    :var 0 orientation: If 0, tree is drawn from left-to-right. If
       1, tree is drawn from right-to-left. This property only makes
       sense when "rect" mode is used.
    
    :var None scale: Scale used to convert branch lengths to
      pixels. If 'None', the scale will be calculated using the
      "tree_width" attribute (read bellow)


    :var 200 tree_width: Total width, in pixels, that tree
      branches are allowed to used. This is, the distance in
      pixels from root to the most distant leaf. If set, this
      value will be used to automatically calculate the branch
      scale.  In practice, increasing this number will cause an
      X-zoom in.

    :var 1 min_leaf_separation: Min separation, in pixels, between
      to adjacent branches

    :var 0 branch_vertical_margin: Leaf branch separation margin,
      in pixels. This will add a separation of X pixels between
      adjacent leaf branches. In practice this produces a Y-zoom
      in.

    :var 0 arc_start: When circular trees are drawn, this defines
      the starting angle (in degrees) from which leaves are
      distribute (clock-wise) around the total arc. 0 = 3 o'clock

    :var 360 arc_span: Total arc used to draw circular trees (in
      degrees)

    :var 0 margin_left: Left tree image margin, in pixels
    :var 0 margin_right: Right tree image margin, in pixels
    :var 0 margin_top: Top tree image margin, in pixels
    :var 0 margin_bottom: Bottom tree image margin, in pixels

    **TREE BRANCHES**

    :var True complete_branch_lines_when_necesary: True or False.
      When top-branch and bottom-branch faces are larger than
      branch length, branch line can be completed. Also, when
      circular trees are drawn
    :var 2 extra_branch_line_type:  0 solid, 1 dashed, 2 dotted
    :var "gray"  extra_branch_line_color": RGB or SVG color name

    
    :var False force_topology: Convert tree branches to a fixed length, thus allowing to
      observe the topology of tight nodes


    :var True draw_guiding_lines: Draw guidelines from leaf nodes
      to aligned faces
    
    :var 2 guiding_lines_type: 0 solid, 1 dashed, 2 dotted
    :var "gray" guiding_lines_color: RGB color code  or SVG color name

    **FACES**

    :var True draw_aligned_faces_as_grid: Aligned faces will be
      drawn as a table, considering all columns in all node faces.

    
    :var False floating_faces_under_tree: By default, floating
      faces are expected to be transparent, so they can be plotted
      directly on the tree image. However, you can also render all
      floating faces under the tree to ensure total tree topology
      visibility

    :var True children_faces_on_top: When floating faces from
      different nodes overlap, children faces are drawn on top of
      parent faces. This can be reversed by setting this attribute
      to false.

    **Addons**

    :var False show_border: Draw a border around the whole tree

    :var True show_scale: Include the scale legend in the tree
      image

    :var False show_leaf_name: Automatically adds a text Face to
      leaf nodes showing their names

    :var False show_branch_length: Automatically adds branch
      length information on top of branches

    :var False show_branch_support: Automatically adds branch
      support text in the bottom of tree branches


    Initialize aligned face headers

    .. currentmodule:: ete_dev.treeview

    :var aligned_header: a :class:`FaceContainer` with the header faces added
      to the aligned faces grid.

    :var aligned_foot: a :class:`FaceContainer` with the foot faces added
      to the aligned faces grid.

    :var legend: a :class:`FaceContainer` with an arbitrary number of faces
      representing the legend of the figure. 
    :var 4 legend_position=4: TopLeft corner if 1, TopRight
      if 2, BottomLeft if 3, BottomRight if 4

    
    :var title: A text string that will be draw as the Tree title

    """
   
    def __init__(self):
        # :::::::::::::::::::::::::
        # TREE SHAPE AND SIZE
        # :::::::::::::::::::::::::
        
        #: Valid modes are : "circular" or "rect"
        self.mode = "rect"

        # Layout function used to dynamically control the aspect of
        # nodes
        self.layout_fn = None
        
        # 0= tree is drawn from left-to-right 1= tree is drawn from
        # right-to-left. This property only has sense when "rect" mode
        # is used.
        self.orientation = 0 

        # Tree rotation in degrees (clock-wise rotation)
        self.rotation = 0 
       
        # Scale used to convert branch lengths to pixels. If 'None',
        # the scale will be calculated using the "tree_width"
        # attribute (read bellow)
        self.scale = None

        # Total width, in pixels, that tree branches are allowed to
        # used. This is, the distance in pixels from root to the most
        # distant leaf. If set, this value will be used to
        # automatically calculate the branch scale.  In practice,
        # increasing this number will cause an X-zoom in.
        self.tree_width = 200

        # Min separation, in pixels, between to adjacent branches
        self.min_leaf_separation = 1 

        # Leaf branch separation margin, in pixels. This will add a
        # separation of X pixels between adjacent leaf branches. In
        # practice this produces a Y-zoom in.
        self.branch_vertical_margin = 0

        # When circular trees are drawn, this defines the starting
        # angle (in degrees) from which leaves are distribute
        # (clock-wise) around the total arc. 0 = 3 o'clock
        self.arc_start = 0 

        # Total arc used to draw circular trees (in degrees)
        self.arc_span = 360

        # Margins around tree picture
        self.margin_left = 1
        self.margin_right = 1
        self.margin_top = 1
        self.margin_bottom = 1

        # :::::::::::::::::::::::::
        # TREE BRANCHES
        # :::::::::::::::::::::::::

        # When top-branch and bottom-branch faces are larger than
        # branch length, branch line can be completed. Also, when
        # circular trees are drawn, 
        self.complete_branch_lines_when_necesary = True
        self.extra_branch_line_type = 2 # 0 solid, 1 dashed, 2 dotted
        self.extra_branch_line_color = "gray" 

        # Convert tree branches to a fixed length, thus allowing to
        # observe the topology of tight nodes
        self.force_topology = False

        # Draw guidelines from leaf nodes to aligned faces
        self.draw_guiding_lines = True

        # Format and color for the guiding lines
        self.guiding_lines_type = 2 # 0 solid, 1 dashed, 2 dotted
        self.guiding_lines_color = "gray"

        # :::::::::::::::::::::::::
        # FACES
        # :::::::::::::::::::::::::

        # Aligned faces will be drawn as a table, considering all
        # columns in all node faces.
        self.draw_aligned_faces_as_grid = True

        # By default, floating faces are expected to be transparent,
        # so they can be plotted directly on the tree image. However,
        # you can also render all floating faces under the tree to
        # ensure total tree topology visibility
        self.floating_faces_under_tree = False

        # When floating faces from different nodes overlap, children
        # faces are drawn on top of parent faces. This can be reversed
        # by setting this attribute to false.
        self.children_faces_on_top = True

        # :::::::::::::::::::::::::
        # Addons
        # :::::::::::::::::::::::::

        # Draw a border around the whole tree
        self.show_border = False

        # Draw the scale 
        self.show_scale = True

        # Initialize aligned face headers
        self.aligned_header = FaceContainer()
        self.aligned_foot = FaceContainer()

        self.show_leaf_name = False
        self.show_branch_length = False
        self.show_branch_support = False

        self.legend = FaceContainer()
        self.legend_position = 2

        # A text string that will be draw as the Tree title
        self.title = FaceContainer()

    def set_layout_fn(self, layout):
        # Validates layout function
        if type(layout) == types.FunctionType or\
                type(layout) == types.MethodType or layout is None:
            self._layout_fn = layout       
            self._layout_handler = layout
        else:
            try:
                self._layout_handler = getattr(layouts, img.layout_fn)
                self._layout_fn = layout       
            except Exception:
                raise ValueError ("Required layout is not a function pointer nor a valid layout name.")
 
    def get_layout_fn(self):
        return self._layout_handler

    layout_fn = property(get_layout_fn, set_layout_fn)
        
class FaceContainer(dict):
    """
    Use this object to create a grid of faces. You can add faces to different columns. 
    """

    def add_face(self, face, column):
        """ 
        add the face **face** to the specified **column**
        """
        self.setdefault(int(column), []).append(face)

def _leaf(node):
    collapsed = hasattr(node, "img_style") and not node.img_style["draw_descendants"]
    return collapsed or node.is_leaf()

def add_face_to_node(face, node, column, aligned=False, position="branch-right"):
    """ 
    .. currentmodule:: ete_dev.treeview.faces

    Adds a Face to a given node. 

    :argument face: A :class:`Face` instance

    .. currentmodule:: ete_dev

    :argument node: a tree node instance (:class:`TreeNode`, :class:`phylo.PhyloNode`, etc.)
    :argument column: An integer number starting from 0
    :argument "branch-right" position: Posible values are "branch-right", "branch-top", "branch-bottom", "aligned" or "float"

   .. warning::

      This function is obsolete. Use :func:`TreeNode.add_face` instead.
   """

    node.img_style.setdefault("_faces", {})
    if position not in FACE_POSITIONS:
        raise (ValueError, "Incorrect position") 
    if aligned:
        position = "aligned"

    node.img_style["_faces"].setdefault(position, {})
    node.img_style["_faces"][position].setdefault(int(column), []).append(face)

def random_color(base=None):
    s = 0.5#random.random()
    v = 0.5+random.random()/2
    s = random.random()
    v = random.random()
    if not base:
        base = random.random()
    R, G, B = map(lambda x: int(100*x), colorsys.hsv_to_rgb(base, s, v))
    return "#%s%s%s" %(hex(R)[2:], hex(G)[2:], hex(B)[2:])


def set_pen_style(pen, line_style):
    if line_style == 0:
        pen.setStyle(QtCore.Qt.SolidLine)
    elif line_style == 1:
        pen.setStyle(QtCore.Qt.DashLine)
    elif line_style == 2:
        pen.setStyle(QtCore.Qt.DotLine)
     
