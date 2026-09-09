"""用 Blender 4.5 制作原创馆员、可编辑源文件、网页 GLB 与真实渲染海报。

运行：blender --background --factory-startup --python assets/character/build_librarian.py
坐标：源文件 Z-up / -Y 朝前；导出的 glTF 为 Y-up / +Z 朝前，脚底为 0。
"""

import json
import math
import struct
from pathlib import Path

import bpy
from mathutils import Matrix, Quaternion, Vector


ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "assets/character"
PUBLIC = ROOT / "web/public"
TAU = math.tau


def material(name, color, roughness=0.65, metallic=0.0):
    """以名字、十六进制 sRGB 颜色及表面参数建立纯 PBR 材质。"""
    values = [int(color[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    linear = [v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in values]
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = (*linear, 1)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*linear, 1)
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    return mat


def parent_to(obj, parent):
    """将物体挂到指定父节点，保留世界坐标。"""
    world = obj.matrix_world.copy()
    obj.parent = parent
    obj.matrix_world = world
    return obj


def empty(name, location, parent=None):
    """建立命名动画枢轴；location 为 Blender 世界坐标。"""
    obj = bpy.data.objects.new(name, None)
    bpy.context.collection.objects.link(obj)
    obj.location = location
    bpy.context.view_layer.update()
    return parent_to(obj, parent) if parent else obj


def finish(obj, name, mat, parent, smooth=True):
    """命名、着色并为几何设置平滑法线和父节点。"""
    obj.name = name
    obj.data.materials.append(mat)
    if smooth and obj.type == "MESH":
        for polygon in obj.data.polygons:
            polygon.use_smooth = True
    bpy.context.view_layer.update()
    return parent_to(obj, parent)


def sphere(name, location, scale, mat, parent, segments=28, rings=18):
    """以中心和三轴比例建立柔和的五官、关节等椭球细节。"""
    bpy.ops.mesh.primitive_uv_sphere_add(segments=segments, ring_count=rings, location=location)
    obj = bpy.context.object
    obj.scale = scale
    return finish(obj, name, mat, parent)


def box(name, location, scale, radius, mat, parent, rotation=None):
    """以全尺寸和圆角半径建立鞋、衣袋等圆角块。"""
    bpy.ops.mesh.primitive_cube_add(size=1, location=location)
    obj = bpy.context.object
    obj.scale = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    bevel = obj.modifiers.new("Soft tailored edge", "BEVEL")
    bevel.width = radius
    bevel.segments = 3
    bpy.ops.object.modifier_apply(modifier=bevel.name)
    if rotation:
        obj.rotation_euler = rotation
    return finish(obj, name, mat, parent)


def mesh(name, vertices, faces, mat, parent, smooth=True):
    """从顶点及面索引生成可编辑网格。"""
    data = bpy.data.meshes.new(name)
    data.from_pydata(vertices, [], faces)
    data.update()
    obj = bpy.data.objects.new(name, data)
    bpy.context.collection.objects.link(obj)
    return finish(obj, name, mat, parent, smooth)


def tube(name, points, radius, mat, parent):
    """通过世界坐标控制点建立细线，再转网格供 glTF 使用。"""
    data = bpy.data.curves.new(name, "CURVE")
    data.dimensions = "3D"
    data.resolution_u = 10
    data.bevel_depth = radius
    data.bevel_resolution = 3
    spline = data.splines.new("BEZIER")
    spline.bezier_points.add(len(points) - 1)
    for point, co in zip(spline.bezier_points, points):
        point.co = co
        point.handle_left_type = "AUTO"
        point.handle_right_type = "AUTO"
    obj = bpy.data.objects.new(name, data)
    bpy.context.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.convert(target="MESH")
    obj.select_set(False)
    return finish(obj, name, mat, parent)


def tailored(name, levels, mat, parent):
    """按 (z, 中心x, 中心y, 宽半径, 深半径) 截面缝合衣裤轮廓。"""
    count = 32
    vertices = []
    for z, x, y, rx, ry in levels:
        for i in range(count):
            angle = TAU * i / count
            vertices.append((x + rx * math.cos(angle), y + ry * math.sin(angle), z))
    faces = [tuple(reversed(range(count)))]
    for j in range(len(levels) - 1):
        for i in range(count):
            n = (i + 1) % count
            faces.append((j * count + i, j * count + n, (j + 1) * count + n, (j + 1) * count + i))
    faces.append(tuple(range((len(levels) - 1) * count, len(levels) * count)))
    obj = mesh(name, vertices, faces, mat, parent)
    bevel = obj.modifiers.new("Tailored soft seams", "BEVEL")
    bevel.width = 0.025
    bevel.segments = 2
    bevel.angle_limit = 0.42
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.modifier_apply(modifier=bevel.name)
    return obj


def limb(name, start, end, radius_start, radius_end, mat, parent):
    """在两个端点间建立连续、渐变半径的袖管或手指。"""
    start, end = Vector(start), Vector(end)
    length = (end - start).length
    obj = tailored(name, [(-length / 2, 0, 0, radius_start * .72, radius_start * .72),
                          (-length / 2 + .04, 0, 0, radius_start, radius_start),
                          (length / 2 - .035, 0, 0, radius_end, radius_end),
                          (length / 2, 0, 0, radius_end * .8, radius_end * .8)], mat, None)
    obj.location = (start + end) / 2
    obj.rotation_mode = "QUATERNION"
    obj.rotation_quaternion = (end - start).to_track_quat("Z", "Y")
    bpy.context.view_layer.update()
    return parent_to(obj, parent)


def validate_glb(path):
    """解析导出 GLB 的实际字节、节点变换和几何边界，打印可复核证据。"""
    data = path.read_bytes()
    magic, version, size = struct.unpack_from("<4sII", data)
    assert (magic, version, size) == (b"glTF", 2, len(data))
    json_size, chunk_type = struct.unpack_from("<II", data, 12)
    assert chunk_type == 0x4E4F534A
    doc = json.loads(data[20:20 + json_size])
    assert len(data) < 3_000_000
    assert not any("uri" in item for kind in ("buffers", "images") for item in doc.get(kind, []))
    names = [node.get("name") for node in doc["nodes"]]
    assert all(names.count(name) == 1 for name in ("Librarian", "Head", "WaveArm", "BookPage"))
    points = []

    def visit(index, parent_matrix):
        """递归累计指定节点与其父级的 glTF 世界变换。"""
        node = doc["nodes"][index]
        if "matrix" in node:
            local = Matrix([node["matrix"][i:i + 4] for i in range(0, 16, 4)]).transposed()
        else:
            rotation = node.get("rotation", [0, 0, 0, 1])
            local = Matrix.LocRotScale(Vector(node.get("translation", [0, 0, 0])),
                                      Quaternion((rotation[3], *rotation[:3])),
                                      Vector(node.get("scale", [1, 1, 1])))
        world = parent_matrix @ local
        if "mesh" in node:
            for primitive in doc["meshes"][node["mesh"]]["primitives"]:
                accessor = doc["accessors"][primitive["attributes"]["POSITION"]]
                for x in (accessor["min"][0], accessor["max"][0]):
                    for y in (accessor["min"][1], accessor["max"][1]):
                        for z in (accessor["min"][2], accessor["max"][2]):
                            points.append(world @ Vector((x, y, z)))
        for child in node.get("children", []):
            visit(child, world)

    for index in doc["scenes"][doc.get("scene", 0)]["nodes"]:
        visit(index, Matrix.Identity(4))
    bounds = [[round(min(p[i] for p in points), 5), round(max(p[i] for p in points), 5)] for i in range(3)]
    assert abs(bounds[1][0]) < .001 and 2.9 < bounds[1][1] < 3.2
    triangles = sum(doc["accessors"][p["indices"]]["count"] // 3 for m in doc["meshes"] for p in m["primitives"])
    vertices = sum(doc["accessors"][p["attributes"]["POSITION"]]["count"] for m in doc["meshes"] for p in m["primitives"])
    print("GLB_VALIDATION", json.dumps({"bytes": size, "nodes": len(names), "meshes": len(doc["meshes"]),
          "materials": len(doc["materials"]), "vertices": vertices, "triangles": triangles,
          "textures": len(doc.get("textures", [])), "bounds_xyz_y_up": bounds,
          "pivots": {name: doc["nodes"][names.index(name)].get("translation", [0, 0, 0])
                     for name in ("Librarian", "Head", "WaveArm", "BookPage")}}))


def build():
    """构建场景并导出受控资产；只写本脚本声明的项目文件。"""
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    bpy.context.preferences.filepaths.save_version = 0
    mats = {
        "skin": material("Warm porcelain clay", "D8A77E", .72),
        "blush": material("Warm cheek glaze", "CA8C72", .78),
        "inner": material("Ear warm shadow", "B97557", .82),
        "hair": material("Espresso sculpted hair", "382C28", .52),
        "hairlight": material("Chestnut hair ridge", "4A3730", .58),
        "green": material("Forest woven cardigan", "365B49", .91),
        "trim": material("Sage knitted ribbing", "51745B", .91),
        "shirt": material("Oatmeal cotton", "ECE3CE", .95),
        "pants": material("Warm ivory canvas", "D8CFB6", .91),
        "shoe": material("Cocoa soft leather", "654B3B", .72),
        "sole": material("Natural rubber", "A58C6A", .85),
        "ink": material("Deep brown eyes and ink", "302822", .5),
        "white": material("Cream eye highlights", "FFF5E3", .36),
        "brass": material("Antique brass eyewear", "B89B64", .32, .65),
        "book": material("Terracotta bookcloth", "AF6244", .86),
        "paper": material("Warm book paper", "F4E8CA", .95),
        "edge": material("Page edge shadow", "CEBD97", .95),
        "ribbon": material("Ochre bookmark", "C59449", .85),
    }
    root = empty("Librarian", (0, 0, 0))
    head = empty("Head", (0, 0, 2.02), root)
    wave = empty("WaveArm", (.36, 0, 1.85), root)
    # 裤腿有膝部、脚踝收口；鞋底恰好落在 z=0。
    for side in (-1, 1):
        x = side * .185
        tailored(f"Canvas trouser {side}", [(.17, x, 0, .125, .135), (.23, x, 0, .135, .15),
                 (.55, x, .015, .14, .16), (.88, x * .95, 0, .15, .19),
                 (1.11, x * .86, 0, .145, .185)], mats["pants"], root)
        box(f"Sole {side}", (x, -.07, .044), (.29, .46, .088), .038, mats["sole"], root)
        box(f"Loafer {side}", (x, -.08, .13), (.285, .425, .17), .072, mats["shoe"], root)
        tube(f"Shoe seam {side}", [(x - .105, -.20, .177), (x, -.25, .195), (x + .105, -.20, .177)], .007, mats["sole"], root)
        tailored(f"Trouser cuff {side}", [(.208, x, 0, .135, .148), (.22, x, 0, .143, .159),
                 (.263, x, 0, .143, .159), (.274, x, 0, .137, .151)], mats["shirt"], root)
    tailored("Continuous cardigan body", [(1.02, 0, 0, .315, .22), (1.08, 0, 0, .34, .24),
             (1.30, 0, 0, .34, .255), (1.65, 0, 0, .37, .255), (1.84, 0, .015, .36, .235),
             (1.94, 0, .02, .265, .19), (1.99, 0, .02, .17, .145)], mats["green"], root)
    tailored("Cardigan knitted hem", [(1.033, 0, 0, .319, .225), (1.046, 0, 0, .342, .245),
             (1.106, 0, 0, .348, .249), (1.118, 0, 0, .34, .242)], mats["trim"], root)
    shirt_rows = [(1.976, .145, -.188), (1.91, .14, -.224), (1.84, .13, -.263),
                  (1.73, .112, -.275), (1.52, .055, -.28), (1.40, .005, -.278)]
    shirt_vertices = [(side * width, y, z) for z, width, y in shirt_rows for side in (-1, 1)]
    mesh("Visible cotton shirt", shirt_vertices, [(i * 2, i * 2 + 1, i * 2 + 3, i * 2 + 2)
         for i in range(len(shirt_rows) - 1)], mats["shirt"], root, False)
    for side in (-1, 1):
        tube(f"Cardigan lapel {side}", [(side * .145, -.18, 1.975), (side * .13, -.257, 1.77),
             (side * .055, -.275, 1.53), (0, -.273, 1.39), (side * .012, -.255, 1.1)], .021, mats["trim"], root)
    for z in (1.21, 1.37):
        sphere("Wood cardigan button", (.015, -.278, z), (.027, .012, .027), mats["brass"], root, 16, 10)
    box("Patch pocket", (-.223, -.243, 1.58), (.17, .035, .19), .025, mats["trim"], root)
    tube("Pocket top stitching", [(-.30, -.272, 1.652), (-.223, -.277, 1.643), (-.15, -.272, 1.652)], .006, mats["shirt"], root)
    # 极小的叶片别针给予独立识别细节，不使用文字或第三方标记。
    leaf = sphere("Leaf pin", (.22, -.233, 1.79), (.024, .013, .054), mats["brass"], root, 16, 10)
    leaf.rotation_euler[1] = -.5
    sphere("Neck", (0, .015, 2.018), (.142, .135, .19), mats["skin"], root)
    # 独立的头部网格做下颌形变；不是简单圆球堆叠。
    face = sphere("Sculpted face", (0, 0, 2.52), (.465, .37, .505), mats["skin"], head, 48, 32)
    for v in face.data.vertices:
        if v.co.z < -.12:
            v.co.x *= 1 - .19 * (-v.co.z)
            v.co.y *= 1 - .10 * (-v.co.z)
    for side in (-1, 1):
        sphere(f"Ear {side}", (side * .445, -.006, 2.5), (.094, .065, .125), mats["skin"], head)
        sphere(f"Ear inset {side}", (side * .481, -.05, 2.505), (.042, .023, .067), mats["inner"], head, 20, 12)
        sphere(f"Cheek {side}", (side * .277, -.303, 2.403), (.081, .018, .039), mats["blush"], head, 24, 14)
        sphere(f"Eye {side}", (side * .177, -.349, 2.565), (.049, .025, .067), mats["ink"], head)
        sphere(f"Eye glint {side}", (side * .177 - .013, -.371, 2.59), (.012, .007, .016), mats["white"], head, 16, 10)
        tube(f"Eyebrow {side}", [(side * .095, -.354, 2.742), (side * .168, -.352, 2.76),
             (side * .255, -.319, 2.744)], .015, mats["hair"], head)
        points = [(side * .181 + .148 * math.cos(TAU * i / 48), -.40, 2.57 + .148 * math.sin(TAU * i / 48)) for i in range(49)]
        tube(f"Round spectacle rim {side}", points, .011, mats["brass"], head)
        tube(f"Spectacle temple {side}", [(side * .327, -.397, 2.59), (side * .435, -.21, 2.60),
             (side * .477, -.045, 2.57)], .009, mats["brass"], head)
    tube("Spectacle bridge", [(-.034, -.404, 2.592), (0, -.419, 2.61), (.034, -.404, 2.592)], .009, mats["brass"], head)
    sphere("Soft nose", (0, -.383, 2.48), (.052, .073, .076), mats["skin"], head)
    tube("Quiet smile", [(-.073, -.349, 2.334), (0, -.366, 2.318), (.073, -.349, 2.339)], .008, mats["inner"], head)
    # 连续发帽加顺向发束，保持后脑、鬓角和偏分刘海的连贯轮廓。
    vertices, faces = [], []
    for j in range(17):
        for i in range(64):
            phi = TAU * i / 64
            frontness = max(0, -math.sin(phi))
            theta_end = 1.69 - .62 * frontness
            theta = .015 + (theta_end - .015) * j / 16
            vertices.append((.477 * math.sin(theta) * math.cos(phi),
                             .389 * math.sin(theta) * math.sin(phi) + .017,
                             2.54 + .532 * math.cos(theta)))
    for j in range(16):
        for i in range(64):
            n = (i + 1) % 64
            faces.append((j * 64 + i, j * 64 + n, (j + 1) * 64 + n, (j + 1) * 64 + i))
    faces.append(tuple(reversed(range(64))))
    mesh("Sculpted hair cap", vertices, faces, mats["hair"], head)
    for i in range(7):
        shift = i * .042
        tube(f"Swept fringe {i}", [(.265 + shift * .3, -.181, 2.948 - shift * .1),
             (.10 - shift * .28, -.317, 3.005 - shift * .25), (-.13 - shift * .4, -.368, 2.925 - shift * .36),
             (-.335 - shift * .10, -.262, 2.749 - shift * .48)], .044 - i * .0025, mats["hair"], head)
    for side in (-1, 1):
        tube(f"Sideburn {side}", [(side * .432, -.075, 2.746), (side * .446, -.102, 2.64),
             (side * .432, -.09, 2.535)], .045, mats["hair"], head)
    # 左臂托书，右臂问候；两臂都有衣袖、袖口与独立手部。
    limb("Book upper sleeve", (-.34, .005, 1.82), (-.49, -.08, 1.44), .16, .128, mats["green"], root)
    limb("Book fore sleeve", (-.49, -.08, 1.44), (-.35, -.39, 1.45), .133, .104, mats["green"], root)
    limb("Book sleeve cuff", (-.367, -.35, 1.45), (-.335, -.421, 1.45), .112, .109, mats["trim"], root)
    sphere("Book supporting palm", (-.28, -.465, 1.454), (.122, .103, .062), mats["skin"], root)
    for i in range(4):
        tube(f"Book finger {i}", [(-.346 + i * .044, -.46, 1.47), (-.35 + i * .044, -.565, 1.48),
             (-.35 + i * .044, -.593, 1.53)], .023, mats["skin"], root)
    limb("Wave upper sleeve", (.34, .005, 1.83), (.61, -.005, 1.6), .159, .12, mats["green"], wave)
    limb("Wave raised sleeve", (.61, -.005, 1.6), (.76, -.025, 1.997), .127, .099, mats["green"], wave)
    limb("Wave ribbed cuff", (.738, -.024, 1.943), (.769, -.027, 2.027), .106, .097, mats["trim"], wave)
    sphere("Wave palm", (.786, -.028, 2.133), (.106, .05, .139), mats["skin"], wave)
    for i, (x, top) in enumerate([(.709, 2.333), (.757, 2.377), (.806, 2.386), (.854, 2.338)]):
        tube(f"Wave finger {i}", [(x, -.026, 2.17), (x - .005 + i * .006, -.034, 2.27),
             (x - .009 + i * .009, -.02, top)], .023, mats["skin"], wave)
        sphere(f"Soft fingertip {i}", (x - .009 + i * .009, -.02, top), (.023, .023, .023),
               mats["skin"], wave, 16, 10)
    tube("Wave thumb", [(.732, -.03, 2.092), (.674, -.049, 2.153), (.647, -.035, 2.212)], .035, mats["skin"], wave)
    # 打开书：纸面沿书脊向两侧上翘，厚度、书边及书签都是真实网格。
    book = empty("OpenBook", (-.09, -.56, 1.53), root)
    bx, by, bz = -.09, -.56, 1.53
    for side in (-1, 1):
        verts = [(bx, by - .23, bz), (bx + side * .465, by - .23, bz + .115),
                 (bx + side * .465, by + .23, bz + .115), (bx, by + .23, bz)]
        cover = mesh(f"Book cover {side}", verts, [(0, 1, 2, 3)], mats["book"], book, False)
        solid = cover.modifiers.new("Bookcloth thickness", "SOLIDIFY")
        solid.thickness = .025
        bpy.context.view_layer.objects.active = cover
        bpy.ops.object.modifier_apply(modifier=solid.name)
        page_verts = [(bx + side * .012, by - .212, bz + .025), (bx + side * .445, by - .212, bz + .132),
                      (bx + side * .445, by + .212, bz + .132), (bx + side * .012, by + .212, bz + .025)]
        page = mesh(f"Paper block {side}", page_verts, [(0, 1, 2, 3)], mats["paper"], book, False)
        solid = page.modifiers.new("Bound paper thickness", "SOLIDIFY")
        solid.thickness = .04
        bpy.context.view_layer.objects.active = page
        bpy.ops.object.modifier_apply(modifier=solid.name)
        for offset in (.012, .021, .032):
            tube(f"Page edge {side} {offset}", [(bx + side * .02, by - .214, bz + offset),
                 (bx + side * .44, by - .214, bz + .105 + offset)], .002, mats["edge"], book)
        for i in range(6):
            start, end = .10, .365 - (i % 3) * .035
            y = by - .14 + i * .048
            tube(f"Printed line {side} {i}", [(bx + side * start, y, bz + .025 + start * .247 + .003),
                 (bx + side * end, y, bz + .025 + end * .247 + .003)], .0025, mats["edge"], book)
    turning = empty("BookPage", (bx, by, bz + .045), book)
    loose = mesh("Loose turning page", [(bx + .009, by - .206, bz + .045), (bx + .40, by - .206, bz + .163),
         (bx + .40, by + .206, bz + .163), (bx + .009, by + .206, bz + .045)], [(0, 1, 2, 3)], mats["paper"], turning, False)
    solid = loose.modifiers.new("Loose paper thickness", "SOLIDIFY")
    solid.thickness = .002
    bpy.context.view_layer.objects.active = loose
    bpy.ops.object.modifier_apply(modifier=solid.name)
    tube("Hanging bookmark", [(bx, by + .05, bz + .05), (bx, by - .225, bz + .025),
         (bx + .01, by - .251, bz - .1), (bx + .022, by - .247, bz - .17)], .014, mats["ribbon"], book)
    bpy.context.view_layer.update()
    # 导出严格选择角色层级，摄影棚不进入网页模型。
    bpy.ops.object.select_all(action="DESELECT")
    character_objects = [root, *root.children_recursive]
    for obj in character_objects:
        obj.select_set(True)
    (PUBLIC / "models").mkdir(parents=True, exist_ok=True)
    (PUBLIC / "images").mkdir(parents=True, exist_ok=True)
    bpy.ops.export_scene.gltf(filepath=str(PUBLIC / "models/librarian.glb"), export_format="GLB",
                             use_selection=True, export_yup=True, export_animations=False,
                             export_cameras=False, export_lights=False, export_extras=True)
    validate_glb(PUBLIC / "models/librarian.glb")
    # 摄影棚与相机仅保留在可编辑 blend，800×1000 PNG 确实来自此模型。
    floor_mat = material("Studio warm linen", "ECE5D8", .95)
    floor = box("Studio floor - not exported", (0, 0, -.09), (200, 200, .18), .02, floor_mat, None)
    bpy.ops.object.camera_add(location=(4.1, -8, 4.2))
    camera = bpy.context.object
    camera.name = "Poster Camera - not exported"
    camera.rotation_euler = (Vector((.05, 0, 1.53)) - camera.location).to_track_quat("-Z", "Y").to_euler()
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = 3.87
    scene = bpy.context.scene
    scene.camera = camera
    for name, location, energy, size, color in [
        ("Large warm key", (-3.5, -4.5, 6.5), 600, 4.5, (1, .91, .79)),
        ("Soft front fill", (4, -2, 4), 350, 3.8, (.84, .91, 1)),
        ("Hair rim", (1.8, 3.5, 5.5), 750, 3.0, (1, .85, .64)),
    ]:
        bpy.ops.object.light_add(type="AREA", location=location)
        light = bpy.context.object
        light.name = name + " - not exported"
        light.data.energy = energy
        light.data.shape = "DISK"
        light.data.size = size
        light.data.color = color
        light.rotation_euler = (Vector((0, 0, 1.5)) - light.location).to_track_quat("-Z", "Y").to_euler()
    scene.world.color = (.22, .22, .22)
    scene.render.engine = "CYCLES"
    scene.cycles.samples = 48
    scene.cycles.use_denoising = True
    scene.render.resolution_x = 800
    scene.render.resolution_y = 1000
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = str(PUBLIC / "images/librarian-poster-v1.png")
    scene.view_settings.view_transform = "AgX"
    scene.view_settings.look = "AgX - Medium High Contrast"
    bpy.ops.wm.save_as_mainfile(filepath=str(ASSETS / "librarian.blend"))
    bpy.ops.render.render(write_still=True)
    bounds = [obj.matrix_world @ Vector(corner) for obj in character_objects if obj.type == "MESH" for corner in obj.bound_box]
    print("LIBRARIAN_BUILD", json.dumps({
        "blender": bpy.app.version_string,
        "mesh_objects": sum(obj.type == "MESH" for obj in character_objects),
        "source_bounds_xyz": [[min(v[i] for v in bounds), max(v[i] for v in bounds)] for i in range(3)],
        "glb_bytes": (PUBLIC / "models/librarian.glb").stat().st_size,
        "poster": str(PUBLIC / "images/librarian-poster-v1.png"),
    }))


if __name__ == "__main__":
    build()
