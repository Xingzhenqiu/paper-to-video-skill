"""Small deterministic scene renderer; authored visuals are never inferred from prose.

Coordinates are normalized within a safe content region. Event times are fractions
of the measured scene duration, so imported speech is never stretched to a template.
Images are fitted with their original aspect ratio; ``focus`` is an explicit crop.
Pillow and imageio-ffmpeg are imported only when rendering is requested.
"""
from functools import lru_cache
import hashlib
import math
from pathlib import Path
import re

VERSION = "0.2.0"
BG = "#10151f"
WHITE = "#eef2f6"
MUTED = "#aab7c7"
TEAL = "#5cc9ce"
YELLOW = "#f1c56c"
VIOLET = "#aa9ed7"
CONTENT = (120.0, 196.0, 1800.0, 852.0)
CAPTION = (140.0, 918.0, 1780.0, 1030.0)
KINDS = {"title", "figure", "diagram", "bar_chart"}
SHAPES = {"cell", "box", "antigen", "receptor"}


def _settings(project):
    # Canonical execution settings live at the record root. Accept nested
    # draft records during migration; core rejects conflicting duplicates.
    if "render" in project:
        return project["render"]
    nested=project.get("project",{}).get("render")
    return nested if nested is not None else {}


def _number(value, name, lo=0, hi=1):
    if type(value) not in (int, float) or not math.isfinite(value) or not lo <= value <= hi:
        raise ValueError(f"{name} must be a finite number from {lo} to {hi}.")
    return float(value)


def _color(value):
    if not isinstance(value, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
        raise ValueError("Visual colors must be six-digit hexadecimal colors.")
    return value


def _inside(base, relative):
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("Asset and font paths must stay inside the project directory.")
    resolved = (base / path).resolve()
    if not resolved.is_relative_to(base.resolve()):
        raise ValueError("Asset path escapes the project directory.")
    return resolved


def content_point(x, y):
    """Map normalized coordinates to the common 1920 x 1080 design canvas."""
    return CONTENT[0] + x * (CONTENT[2] - CONTENT[0]), CONTENT[1] + y * (CONTENT[3] - CONTENT[1])


def fit_box(image_size, box):
    """Return an aspect-preserving centered box, with no stretching or clipping."""
    iw, ih = image_size
    if iw <= 0 or ih <= 0 or box[2] <= box[0] or box[3] <= box[1]:
        raise ValueError("Image and layout dimensions must be positive.")
    scale = min((box[2] - box[0]) / iw, (box[3] - box[1]) / ih)
    width, height = iw * scale, ih * scale
    cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    return cx - width / 2, cy - height / 2, cx + width / 2, cy + height / 2


def validate_visual(project, scene):
    """Validate supported authored grammar before synthesis or encoding begins."""
    visual = scene.get("visual")
    if not isinstance(visual, dict) or visual.get("kind") not in KINDS:
        raise ValueError(f"Unsupported visual kind; choose one of {sorted(KINDS)}.")
    kind = visual["kind"]
    if any(not isinstance(visual.get(field, ""), str) for field in ("title", "subtitle", "caption")):
        raise ValueError("Visual titles and captions must be strings.")
    if not isinstance(scene.get("display_text", ""), str):
        raise ValueError("display_text must be a string.")
    if kind == "title" and not visual.get("title"):
        raise ValueError("A title scene requires title text.")
    if kind == "figure":
        asset_id = visual.get("asset")
        assets = _settings(project).get("assets", {})
        if asset_id not in assets:
            raise ValueError(f"Unknown figure asset: {asset_id}.")
        metadata = assets[asset_id]
        if not isinstance(metadata, dict) or not metadata.get("path"):
            raise ValueError("Figure asset requires a relative path.")
        _inside(Path(project.get("_base_dir", ".")), metadata["path"])
        focus = visual.get("focus")
        if focus is not None:
            if not isinstance(focus, list) or len(focus) != 4:
                raise ValueError("Figure focus must contain normalized left, top, right, bottom.")
            for value in focus:
                _number(value, "focus bound")
            if focus[0] >= focus[2] or focus[1] >= focus[3]:
                raise ValueError("Figure focus must have positive width and height.")
            start = _number(visual.get("focus_start", .2), "focus_start")
            end = _number(visual.get("focus_end", .65), "focus_end")
            if start >= end:
                raise ValueError("focus_start must precede focus_end.")
    if kind == "diagram":
        nodes = visual.get("nodes", [])
        if not isinstance(nodes, list) or not nodes:
            raise ValueError("A diagram requires authored nodes.")
        identities = set()
        for node in nodes:
            if not isinstance(node, dict) or not isinstance(node.get("id"), str) or not node["id"]:
                raise ValueError("Every node needs a nonempty string id.")
            if node["id"] in identities:
                raise ValueError("Diagram node ids must be unique.")
            identities.add(node["id"])
            if node.get("shape") not in SHAPES:
                raise ValueError(f"Unsupported node shape: {node.get('shape')}.")
            _number(node.get("x"), "node x")
            _number(node.get("y"), "node y")
            _number(node.get("size", .13), "node size", .025, .38)
            _color(node.get("color", TEAL))
            if not isinstance(node.get("label", ""), str):
                raise ValueError("Node labels must be strings.")
        for edge in visual.get("edges", []):
            if edge.get("source") not in identities or edge.get("target") not in identities:
                raise ValueError("Every edge must connect existing diagram nodes.")
            _color(edge.get("color", MUTED))
        for event in visual.get("events", []):
            if event.get("target") not in identities or event.get("kind") not in {"reveal", "fade", "highlight", "move"}:
                raise ValueError("Animation events require an existing target and a supported kind.")
            start = _number(event.get("start", 0), "event start")
            end = _number(event.get("end", 1), "event end")
            if start >= end:
                raise ValueError("Animation event start must precede its end.")
            for name in ("from_x", "from_y", "to_x", "to_y"):
                if name in event:
                    _number(event[name], name)
    if kind == "bar_chart":
        bars = visual.get("bars", [])
        if not isinstance(bars, list) or not 1 <= len(bars) <= 6:
            raise ValueError("A bar chart needs one to six authored bars.")
        maximum = _number(visual.get("max_value", 1), "max_value", 1e-12, 1e15)
        for bar in bars:
            _number(bar.get("value"), "bar value", 0, maximum)
            _color(bar.get("color", TEAL))
            if not isinstance(bar.get("label", ""), str):
                raise ValueError("Bar labels must be strings.")
    return {"kind": kind, "node_count": len(visual.get("nodes", [])), "asset": visual.get("asset")}


def ease(value):
    value = min(1, max(0, value))
    return value * value * (3 - 2 * value)


def node_state(node, events, progress):
    """Compute deterministic opacity, highlight and position for a diagram node."""
    state = {"opacity": 1.0, "highlight": 0.0, "x": node["x"], "y": node["y"]}
    for event in events:
        if event["target"] != node["id"]:
            continue
        u = ease((progress - event.get("start", 0)) / (event.get("end", 1) - event.get("start", 0)))
        if event["kind"] == "reveal":
            state["opacity"] *= u
        elif event["kind"] == "fade":
            state["opacity"] *= 1 - u
        elif event["kind"] == "highlight":
            state["highlight"] = math.sin(math.pi * u) if event.get("pulse") else u
        else:
            for axis in ("x", "y"):
                source = event.get("from_" + axis, state[axis])
                target = event.get("to_" + axis, node[axis])
                state[axis] = source + (target - source) * u
    return state


@lru_cache(maxsize=128)
def _font(size, path):
    from PIL import ImageFont
    return ImageFont.truetype(path, size) if path else ImageFont.load_default(size=size)


class Canvas:
    def __init__(self, width, supersample, font_path=None):
        from PIL import Image, ImageDraw
        self.width = width
        self.height = round(width * 9 / 16)
        self.scale = width / 1920 * supersample
        self.image = Image.new("RGB", (round(1920 * self.scale), round(1080 * self.scale)), BG)
        self.draw = ImageDraw.Draw(self.image)
        self.font_path = str(font_path) if font_path else None

    def rgb(self, color, alpha=1):
        _color(color)
        background = (16, 21, 31)
        foreground = tuple(int(color[i:i+2], 16) for i in (1, 3, 5))
        return tuple(round(b + (f - b) * alpha) for b, f in zip(background, foreground))

    def line(self, points, color, width=3, alpha=1):
        self.draw.line([(x*self.scale, y*self.scale) for x, y in points], fill=self.rgb(color, alpha), width=max(1, round(width*self.scale)), joint="curve")

    def ellipse(self, box, fill, outline=None, width=2, alpha=1):
        self.draw.ellipse(tuple(v*self.scale for v in box), fill=self.rgb(fill, alpha), outline=self.rgb(outline, alpha) if outline else None, width=max(1, round(width*self.scale)))

    def rounded(self, box, fill, outline=None, radius=16, width=2, alpha=1):
        self.draw.rounded_rectangle(tuple(v*self.scale for v in box), radius=radius*self.scale, fill=self.rgb(fill, alpha), outline=self.rgb(outline, alpha) if outline else None, width=max(1, round(width*self.scale)))

    def text(self, x, y, value, size=42, color=WHITE, anchor="mm", alpha=1):
        self.draw.text((x*self.scale, y*self.scale), value, font=_font(max(1, round(size*self.scale)), self.font_path), fill=self.rgb(color, alpha), anchor=anchor)

    def text_width(self, value, size):
        return self.draw.textlength(value, font=_font(max(1, round(size*self.scale)), self.font_path))/self.scale

    def paragraph(self, value, box, size=48, minimum=40, color=WHITE, max_lines=2, alpha=1):
        if not value:
            return
        width = box[2] - box[0]
        for actual in range(size, minimum-1, -1):
            lines = []
            for paragraph in value.splitlines():
                words = paragraph.split() if " " in paragraph else list(paragraph)
                separator = " " if " " in paragraph else ""
                line = ""
                for word in words:
                    candidate = line + separator + word if line else word
                    if self.text_width(candidate, actual) <= width:
                        line = candidate
                    else:
                        if not line or self.text_width(word, actual) > width:
                            break
                        lines.append(line)
                        line = word
                else:
                    lines.append(line)
                    continue
                lines = [value] * (max_lines + 1)
                break
            if len(lines) <= max_lines and len(lines)*actual*1.25 <= box[3]-box[1]:
                cy = (box[1]+box[3])/2
                for i, line in enumerate(lines):
                    self.text((box[0]+box[2])/2, cy+(i-(len(lines)-1)/2)*actual*1.25, line, actual, color, alpha=alpha)
                return
        raise ValueError("Text exceeds the readable safe area; shorten it or split the scene.")

    def finish(self):
        from PIL import Image
        return self.image.resize((self.width, self.height), Image.Resampling.LANCZOS)


def _dark(color, amount=.25):
    return "#" + "".join(f"{round(int(color[i:i+2],16)*amount):02x}" for i in (1,3,5))


def _organic(c, x, y, radius, color, opacity, highlight=0):
    points = []
    for i in range(81):
        angle = 2*math.pi*i/80
        radial = radius*(1+.043*math.sin(angle*5+.7)+.028*math.sin(angle*3-1.2))
        points.append((x+radial*math.cos(angle), y+radial*.91*math.sin(angle)))
    c.draw.polygon([(px*c.scale,py*c.scale) for px,py in points], fill=c.rgb(_dark(color,.32),opacity))
    c.line(points,color,3.4+2*highlight,opacity)
    inner = [(x+(px-x)*.94,y+(py-y)*.94) for px,py in points]
    c.line(inner,_dark(color,.65),1.7,opacity)
    nr = radius*.38
    c.ellipse((x-nr*.7,y-nr*1.2,x+nr*1.3,y+nr*.55),_dark(color,.6),color,1.8,opacity)
    # A few membrane markers communicate a cell surface, rather than a plain circle.
    for angle in (.3,1.65,3.15,4.8):
        ux,uy=math.cos(angle),math.sin(angle)
        start=(x+radius*ux,y+radius*.91*uy)
        end=(x+radius*1.12*ux,y+radius*1.02*uy)
        c.line([start,end],color,2,opacity)
        c.ellipse((end[0]-3,end[1]-3,end[0]+3,end[1]+3),color,alpha=opacity)


def _node(c,node,state):
    x,y=content_point(state["x"],state["y"])
    radius=node.get("size",.13)*(CONTENT[3]-CONTENT[1])
    color=node.get("color",TEAL)
    alpha=state["opacity"]
    if alpha <= .001:
        return
    shape=node["shape"]
    label=node.get("label","")
    if shape=="cell":
        _organic(c,x,y,radius,color,alpha,state["highlight"])
        if label:
            c.text(x,y+radius*1.27,label,34,color,alpha=alpha)
    elif shape=="antigen":
        points=[]
        for i in range(49):
            angle=2*math.pi*i/48
            r=radius*(.82+.11*math.cos(angle*6))
            points.append((x+r*math.cos(angle),y+r*math.sin(angle)))
        c.draw.polygon([(px*c.scale,py*c.scale) for px,py in points],fill=c.rgb(_dark(color,.4),alpha))
        c.line(points,color,3+3*state["highlight"],alpha)
        if label:
            c.text(x,y+radius*1.25,label,34,color,alpha=alpha)
    elif shape=="receptor":
        # Single-chain two-domain symbol, never a Y-shaped whole-antibody icon.
        dw=radius*.43
        c.rounded((x-radius*.66,y-radius*.82,x-radius*.66+dw,y+radius*.18),_dark(color,.6),color,18,2.5,alpha)
        c.rounded((x+radius*.23,y-radius*.82,x+radius*.23+dw,y+radius*.18),_dark(color,.6),color,18,2.5,alpha)
        points=[]
        for i in range(17):
            t=i/16
            points.append((x-radius*.45+radius*.45*t,y-radius*.84-radius*.3*math.sin(math.pi*t)))
        for i in range(17):
            t=i/16
            points.append((x+radius*.22*t,y-radius*.84+radius*1.08*t))
        for i in range(17):
            t=i/16
            points.append((x+radius*.22+radius*.24*t,y+radius*.24+radius*.14*math.sin(math.pi*t)))
        c.line(points,color,4.2,alpha)
        c.line([(x-radius*.45,y+radius*.2),(x-radius*.45,y+radius*.83)],color,5,alpha)
        if label:
            c.text(x,y+radius*1.16,label,34,color,alpha=alpha)
    else:
        c.rounded((x-radius*1.2,y-radius*.55,x+radius*1.2,y+radius*.55),_dark(color,.33),color,20,2.5+state["highlight"]*2,alpha)
        if label:
            size=38
            while size>28 and c.text_width(label,size)>radius*2.14:
                size-=1
            if c.text_width(label,size)>radius*2.14:
                raise ValueError("Box label is too long; enlarge the node or shorten the label.")
            c.text(x,y,label,size,color,alpha=alpha)


def _edge(c,edge,nodes,states):
    source,target=nodes[edge["source"]],nodes[edge["target"]]
    sa,ta=states[source["id"]],states[target["id"]]
    alpha=min(sa["opacity"],ta["opacity"])
    if alpha <= .001:
        return
    x1,y1=content_point(sa["x"],sa["y"])
    x2,y2=content_point(ta["x"],ta["y"])
    distance=math.hypot(x2-x1,y2-y1)
    if distance < 1:
        return
    ux,uy=(x2-x1)/distance,(y2-y1)/distance
    r1=source.get("size",.13)*(CONTENT[3]-CONTENT[1])*1.2
    r2=target.get("size",.13)*(CONTENT[3]-CONTENT[1])*1.2
    if r1+r2+15 >= distance:
        return
    a,b=(x1+ux*r1,y1+uy*r1),(x2-ux*r2,y2-uy*r2)
    color=edge.get("color",MUTED)
    c.line([a,b],color,3,alpha)
    if edge.get("arrow",True):
        c.line([(b[0]-ux*14-uy*8,b[1]-uy*14+ux*8),b,(b[0]-ux*14+uy*8,b[1]-uy*14-ux*8)],color,3,alpha)
    if edge.get("label"):
        cx,cy=(a[0]+b[0])/2+uy*27,(a[1]+b[1])/2-ux*27
        width=c.text_width(edge["label"],28)+20
        c.rounded((cx-width/2,cy-21,cx+width/2,cy+21),BG,radius=6)
        c.text(cx,cy,edge["label"],28,MUTED,alpha=alpha)


class FrameRenderer:
    def __init__(self,project,scene,width=1920,duration=1):
        validate_visual(project,scene)
        self.project,self.scene,self.width,self.duration=project,scene,width,duration
        self.visual=scene["visual"]
        self.font_path=None
        settings=_settings(project)
        self.supersample=_number(settings.get("supersample",1.5),"supersample",1,3)
        if settings.get("font"):
            self.font_path=_inside(Path(project.get("_base_dir",".")),settings["font"])
            if not self.font_path.is_file():
                raise ValueError("Configured font is missing from the project.")
        self.asset=None
        if self.visual["kind"]=="figure":
            from PIL import Image
            entry=settings["assets"][self.visual["asset"]]
            asset=_inside(Path(project.get("_base_dir",".")),entry["path"])
            if not asset.is_file():
                raise ValueError("Figure asset is missing.")
            if not entry.get("sha256") or hashlib.sha256(asset.read_bytes()).hexdigest()!=entry["sha256"]:
                raise ValueError("Figure asset changed; review it and update its expected hash.")
            with Image.open(asset) as opened:
                self.asset=opened.convert("RGBA")

    def frame(self,seconds):
        from PIL import Image
        c=Canvas(self.width,self.supersample,self.font_path)
        visual=self.visual
        progress=max(0,min(1,seconds/self.duration))
        kind=visual["kind"]
        if kind=="title":
            c.paragraph(visual["title"],(160,330,1760,510),86,64,max_lines=2)
            c.paragraph(visual.get("subtitle",""),(260,542,1660,670),42,36,TEAL,max_lines=2)
        else:
            c.paragraph(visual.get("title",""),(140,58,1780,159),59,44,max_lines=1)
        if kind=="figure":
            bounds=(0,0,1,1)
            focus=visual.get("focus")
            if focus:
                amount=ease((progress-visual.get("focus_start",.2))/(visual.get("focus_end",.65)-visual.get("focus_start",.2)))
                bounds=tuple(a+(b-a)*amount for a,b in zip(bounds,focus))
            iw,ih=self.asset.size
            crop=self.asset.crop((round(bounds[0]*iw),round(bounds[1]*ih),round(bounds[2]*iw),round(bounds[3]*ih)))
            box=fit_box(crop.size,CONTENT)
            pixel_box=tuple(round(v*c.scale) for v in box)
            crop=crop.resize((pixel_box[2]-pixel_box[0],pixel_box[3]-pixel_box[1]),Image.Resampling.LANCZOS)
            c.image.paste(crop,pixel_box[:2],crop)
        elif kind=="diagram":
            nodes={node["id"]:node for node in visual["nodes"]}
            states={key:node_state(node,visual.get("events",[]),progress) for key,node in nodes.items()}
            for edge in visual.get("edges",[]):
                _edge(c,edge,nodes,states)
            for key,node in nodes.items():
                _node(c,node,states[key])
        elif kind=="bar_chart":
            bars=visual["bars"]
            maximum=visual.get("max_value",1)
            x0,x1=460,1480
            top,bottom=300,780
            for tick in (0,.5,1):
                x=x0+(x1-x0)*tick
                c.line([(x,top-20),(x,bottom+10)],"#283346",1.5)
                c.text(x,top-48,f"{maximum*tick:g}",28,MUTED)
            row=(bottom-top)/len(bars)
            growth=ease(progress/.55)
            for i,bar in enumerate(bars):
                y=top+(i+.5)*row
                color=bar.get("color",TEAL)
                c.text(x0-35,y,bar.get("label",""),36,color,"rm")
                end=x0+(x1-x0)*bar["value"]/maximum*growth
                if end>x0+1:
                    c.rounded((x0,y-25,end,y+25),color,radius=min(12,(end-x0)/2))
                if growth>.98:
                    c.text(end+24,y,f"{bar['value']:g}",36,color,"lm")
        caption=self.scene.get("display_text") or visual.get("caption","")
        c.paragraph(caption,CAPTION,46,40,max_lines=2)
        # Very brief uniform blending avoids decorative transition machinery.
        fade=min(.18,self.duration*.05)
        opacity=.6+.4*min(ease(seconds/fade),ease((self.duration-seconds)/fade))
        if opacity<.999:
            background=Image.new("RGB",c.image.size,BG)
            c.image=Image.blend(background,c.image,opacity)
        return c.finish()


def render_frame(project,scene,seconds,duration,width=1920):
    """Return a Pillow image for human preview without encoding a video."""
    duration=_number(duration,"duration",1e-4,36000)
    return FrameRenderer(project,scene,width,duration).frame(seconds)


def render_scene(project,scene,output_mp4,duration,width=1920,fps=24):
    """Encode one authored silent scene at the supplied measured-audio duration."""
    duration=_number(duration,"duration",1e-4,36000)
    if type(width) is not int or width<320 or width%32:
        raise ValueError("Render width must be a multiple of 32 and at least 320.")
    if type(fps) is not int or not 1<=fps<=60:
        raise ValueError("Frame rate must be an integer from 1 to 60.")
    renderer=FrameRenderer(project,scene,width,duration)
    frame_count=max(1,round(duration*fps))
    output=Path(output_mp4)
    output.parent.mkdir(parents=True,exist_ok=True)
    import imageio_ffmpeg
    writer=imageio_ffmpeg.write_frames(str(output),(width,round(width*9/16)),fps=fps,codec="libx264",pix_fmt_in="rgb24",pix_fmt_out="yuv420p",macro_block_size=2,output_params=["-crf","18","-preset","medium","-movflags","+faststart"])
    try:
        writer.send(None)
        for index in range(frame_count):
            writer.send(renderer.frame(index/fps).tobytes())
    finally:
        writer.close()
    return {"frames":frame_count,"duration":frame_count/fps,"width":width,"height":round(width*9/16),"fps":fps,"sha256":hashlib.sha256(output.read_bytes()).hexdigest(),"renderer_version":VERSION}
