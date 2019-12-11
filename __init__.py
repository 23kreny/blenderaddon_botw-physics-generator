# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTIBILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.

bl_info = {
    "name": "Physics Generator",
    "author": "kreny",
    "description": "",
    "blender": (2, 80, 0),
    "version": (0, 1, 3),
    "location": "",
    "warning": "",
    "category": "Breath of the Wild",
}

import os
import subprocess
from math import radians

import bpy
import mathutils
from bpy.props import (
    BoolProperty,
    EnumProperty,
    StringProperty,
    IntProperty,
    FloatProperty,
)
from bpy.types import Operator
from bpy_extras.io_utils import ExportHelper, ImportHelper


def ShowMessageBox(title, message, icon="INFO"):
    def draw(self, context):
        self.layout.label(text=message)

    bpy.context.window_manager.popup_menu(draw, title=title, icon=icon)


def parse_physics(context, filepath):
    filepath_obj = filepath + ".obj"
    output = ""
    obj_num = 0
    obj_template = "o Shape_{}\n"
    vert_template = "v {} {} {}\n"

    with open(filepath, "r") as f:
        for line in f.readlines():
            line = line.lstrip()
            if line.startswith("vertex_num"):
                output += obj_template.format(obj_num)
                obj_num += 1
            elif line.startswith("vertex_"):
                split = line.split("[")
                strip = split[1].rstrip("\n")
                strip = strip.rstrip("]")
                coords = strip.split(", ")
                output += vert_template.format(*coords)

    with open(filepath_obj, "w") as f:
        f.write(output)

    try:
        bpy.ops.import_scene.obj("EXEC_DEFAULT", filepath=filepath_obj)
    except Exception as e:
        print(e)
        ShowMessageBox(".OBJ Import Error", f"{e}")
        return {"CANCELLED"}
    try:
        os.remove(filepath_obj)
    except Exception as e:
        print(e)
    return {"FINISHED"}


def generate_physics(
    context,
    filepath: str,
    physics_type: str,
    vhacd: bool,
    vhacd_params: list,
    remove_hulls_after_export: bool,
    binary: bool = False,
):
    scene = bpy.context.scene
    if not scene.objects:
        ShowMessageBox("No objects exist", "What are you up to?")
        return {"CANCELLED"}

    if vhacd:
        try:
            bpy.ops.object.select_all(action="SELECT")
            bpy.ops.object.vhacd(
                "EXEC_DEFAULT",
                remove_doubles=vhacd_params[0],
                apply_transforms=vhacd_params[1],
                resolution=vhacd_params[2],
                depth=vhacd_params[3],
                concavity=vhacd_params[4],
                planeDownsampling=vhacd_params[5],
                convexhullDownsampling=vhacd_params[6],
                alpha=vhacd_params[7],
                beta=vhacd_params[8],
                gamma=vhacd_params[9],
                pca=vhacd_params[10],
                mode=vhacd_params[11],
                maxNumVerticesPerCH=vhacd_params[12],
                minVolumePerCH=vhacd_params[13],
            )
        except Exception as e:
            ShowMessageBox("V-HACD Error", f"{e}")
            return {"CANCELLED"}
    else:
        objects = [obj for obj in scene.objects if "_hull_" in obj.name]
        if not objects:
            ShowMessageBox(
                "No convex hulls found",
                "You probably didn't generate your collisions, dummy.",
            )
            return {"CANCELLED"}

    if binary:
        filepath_yml = filepath.replace(".bphysics", ".physics.yml")
        filepath_bin = filepath
    else:
        filepath_yml = filepath
    script_file = os.path.realpath(__file__)
    directory = os.path.dirname(script_file)
    default_file = os.path.join(
        directory, "weapon.yml" if physics_type == "WEAPON" else "default.yml"
    )
    with open(default_file, "r") as f:
        content = f.read()

    if physics_type == "WEAPON":
        vertex_template = "                      vertex_{0}: !vec3 [{1}, {2}, {3}]"

        shape_template_metal = (
            "                    ShapeParam_{0}: !obj\n"
            "                      shape_type: !str32 polytope\n"
            "                      vertex_num: {1}\n"
            "{2}\n"
            "                      material: !str32 {3}\n"
            "                      sub_material: !str32 {4}\n"
            "                      wall_code: !str32 {5}\n"
            "                      floor_code: !str32 {6}\n"
        )

        shape_template_u = (
            "                    ShapeParam_{0}: !obj\n"
            "                      shape_type: !str32 polytope\n"
            "                      vertex_num: {1}\n"
            "{2}\n"
            "                      material: !str32 Undefined\n"
            "                      sub_material: !str32 Undefined\n"
            "                      wall_code: !str32 None\n"
            "                      floor_code: !str32 None\n"
        )

        hulls = [obj for obj in scene.objects if "_hull_" in obj.name]

        shapes_metal = ""
        shapes_u = ""
        for i, hull in enumerate(hulls):
            mtx = mathutils.Matrix.Rotation(radians(-90.0), 4, "X") @ hull.matrix_world
            vertices = [mtx @ v.co for v in hull.data.vertices]
            shapes_metal += shape_template_metal.format(
                i,
                len(vertices),
                "\n".join(
                    [
                        vertex_template.format(o, co.x, co.y, co.z)
                        for o, co in enumerate(vertices)
                    ]
                ),
                hull.get("botw_material") if hull.get("botw_material") else "Metal",
                hull.get("botw_sub_material")
                if hull.get("botw_sub_material")
                else "Metal_Heavy",
                hull.get("botw_wall_code") if hull.get("botw_wall_code") else "None",
                hull.get("botw_floor_code") if hull.get("botw_floor_code") else "None",
            )
            shapes_u += shape_template_u.format(
                i,
                len(vertices),
                "\n".join(
                    [
                        vertex_template.format(o, co.x, co.y, co.z)
                        for o, co in enumerate(vertices)
                    ]
                ),
            )

        output = content.format(len(hulls), shapes_metal, shapes_u)
    elif physics_type in ("FIXED", "DYNAMIC"):
        rigid_body_template = (
            "                RigidBody_{0}: !list\n"
            "                  objects:\n"
            "                    948250248: !obj\n"
            "                      rigid_body_name: !str64 {1}\n"
            "                      mass: 10000.0\n"
            "                      inertia: !vec3 [6666.67, 6666.67, 6666.67]\n"
            "                      linear_damping: 0.0\n"
            "                      angular_damping: 0.05\n"
            "                      max_impulse: 10000.0\n"
            "                      col_impulse_scale: 1.0\n"
            "                      ignore_normal_for_impulse: false\n"
            "                      volume: 8.0\n"
            "                      toi: true\n"
            "                      center_of_mass: !vec3 [0.0, 1.0, 0.0]\n"
            "                      max_linear_velocity: 200.0\n"
            "                      bounding_center: !vec3 [0.0, 1.0, 0.0]\n"
            "                      bounding_extents: !vec3 [2.0, 2.0, 2.0]\n"
            "                      max_angular_velocity_rad: 198.968\n"
            "                      motion_type: !str32 {4}\n"
            "                      contact_point_info: !str32 Body\n"
            "                      collision_info: !str32 Body\n"
            "                      bone: !str64 \n"
            "                      water_buoyancy_scale: 1.0\n"
            "                      water_flow_effective_rate: 1.0\n"
            "                      layer: !str32 Entity{5}Object\n"
            "                      no_hit_ground: false\n"
            "                      no_hit_water: false\n"
            "                      groundhit: !str32 HitAll\n"
            "                      use_ground_hit_type_mask: false\n"
            "                      no_char_standing_on: false\n"
            "                      navmesh: !str32 {6}\n"
            "                      navmesh_sub_material: !str32 \n"
            "                      link_matrix: ''\n"
            "                      magne_mass_scaling_factor: 1.0\n"
            "                      always_character_mass_scaling: false\n"
            "                      shape_num: {2}\n"
            "{3}"
            "                  lists: {{}}\n"
        )

        shape_param_template = (
            "                    ShapeParam_{0}: !obj #{1}\n"
            "                      shape_type: !str32 polytope\n"
            "                      vertex_num: {2}\n"
            "{3}\n"
            "                      material: !str32 {4}\n"
            "                      sub_material: !str32 {5}\n"
            "                      wall_code: !str32 {6}\n"
            "                      floor_code: !str32 {7}\n"
        )

        vertex_template = "                      vertex_{0}: !vec3 [{1}, {2}, {3}]"

        result = ""

        rigid_bodies = ""

        non_hull_objects = [
            obj
            for obj in scene.objects
            if (not ("_hull_" in obj.name)) and (obj.type == "MESH")
        ]
        if not non_hull_objects:
            ShowMessageBox("ERROR", "You need to keep the original mesh.")
            return {"CANCELLED"}
        non_hull_index = 0
        hulls = []
        for obj in non_hull_objects:
            shape_hull_index = 0
            shapes = ""
            obj_material = (
                obj.get("botw_material") if obj.get("botw_material") else "Metal"
            )
            obj_sub_material = (
                obj.get("botw_sub_material")
                if obj.get("botw_sub_material")
                else "Metal_Heavy"
            )
            obj_wall_code = (
                obj.get("botw_wall_code") if obj.get("botw_wall_code") else "NoClimb"
            )
            obj_floor_code = (
                obj.get("botw_floor_code") if obj.get("botw_floor_code") else "None"
            )
            for shape_hull in set(scene.objects) - set(non_hull_objects):
                if not (shape_hull.name.split("_hull_")[0] == obj.name):
                    continue
                hulls.append(shape_hull)
                # fmt: off
                mtx = (
                    mathutils.Matrix.Rotation(radians(-90.0), 4, "X") \
                    @ shape_hull.matrix_world
                )
                # fmt: on
                verts = [mtx @ v.co for v in shape_hull.data.vertices]
                shapes += shape_param_template.format(
                    shape_hull_index,
                    shape_hull.name,
                    len(verts),
                    "\n".join(
                        [
                            vertex_template.format(o, co.x, co.y, co.z)
                            for o, co in enumerate(verts)
                        ]
                    ),
                    shape_hull.get("botw_material")
                    if shape_hull.get("botw_material")
                    else obj_material,
                    shape_hull.get("botw_sub_material")
                    if shape_hull.get("botw_sub_material")
                    else obj_sub_material,
                    shape_hull.get("botw_wall_code")
                    if shape_hull.get("botw_wall_code")
                    else obj_wall_code,
                    shape_hull.get("botw_floor_code")
                    if shape_hull.get("botw_floor_code")
                    else obj_floor_code,
                )
                shape_hull_index += 1
            rigid_bodies += rigid_body_template.format(
                non_hull_index,
                obj.name,
                shape_hull_index,
                shapes,
                physics_type.capitalize(),
                "Ground" if physics_type.capitalize() == "Fixed" else "",
                "STATIC_WALKABLE_AND_CUTTING"
                if physics_type.capitalize() == "Fixed"
                else "DYNAMIC_SILHOUETTE_AND_OBSTACLE",
            )
            non_hull_index += 1
        output = content.format(non_hull_index, rigid_bodies.rstrip("\n"))
    else:
        ShowMessageBox("Something is wrong", "Huh?")
        return {"CANCELLED"}

    with open(filepath_yml, "w") as output_file:
        output_file.write(output)

    if binary:
        try:
            command = "aamp {} {}".format(filepath_yml, filepath_bin)
            print(subprocess.check_output(command, shell=True))
        except Exception as e:
            print(e)
            ShowMessageBox(
                "AAMP Error", "Make sure you have AAMP installed (pip install aamp)",
            )
            return {"CANCELLED"}
        finally:
            os.remove(filepath_yml)
    if vhacd and remove_hulls_after_export:
        bpy.ops.object.select_all(action="DESELECT")
        for hull in hulls:
            hull.select_set(True)
        bpy.ops.object.delete()
    return {"FINISHED"}


class SelectParams(Operator):
    """Select various parameters for BotW physics meshes"""

    bl_idname = "botw.select_params"
    bl_label = "Select BotW physics parameters"
    bl_description = "Choose physics parameters for your shapes"
    bl_options = {"REGISTER", "UNDO"}

    material: EnumProperty(
        name="Material",
        description="Material of the object",
        items=(
            ("AirWall", "AirWall", "AirWall"),
            ("Barrier", "Barrier", "Barrier"),
            ("Bone", "Bone", "Bone"),
            ("CharControl", "CharControl", "CharControl"),
            ("Cloth", "Cloth", "Cloth"),
            ("Conveyer", "Conveyer", "Conveyer"),
            ("Glass", "Glass", "Glass"),
            ("Grass", "Grass", "Grass"),
            ("Grudge", "Grudge", "Grudge"),
            ("GuardianFoot", "GuardianFoot", "GuardianFoot"),
            ("Ice", "Ice", "Ice"),
            ("LaunchPad", "LaunchPad", "LaunchPad"),
            ("Lava", "Lava", "Lava"),
            ("MagicBall", "MagicBall", "MagicBall"),
            ("Meat", "Meat", "Meat"),
            ("Metal", "Metal", "Metal"),
            ("Misc", "Misc", "Misc"),
            ("Ragdoll", "Ragdoll", "Ragdoll"),
            ("Rope", "Rope", "Rope"),
            ("Snow", "Snow", "Snow"),
            ("Soil", "Soil", "Soil"),
            ("Stone", "Stone", "Stone"),
            ("Surfing", "Surfing", "Surfing"),
            ("Undefined", "Undefined", "Undefined"),
            ("Vegetable", "Vegetable", "Vegetable"),
            ("Water", "Water", "Water"),
            ("WireNet", "WireNet", "WireNet"),
            ("Wood", "Wood", "Wood"),
        ),
        default="Metal",
    )

    sub_material: EnumProperty(
        name="Sub Material",
        description="Sub material of the object",
        items=(
            ("AirWall", "AirWall", "AirWall"),
            ("Bone", "Bone", "Bone"),
            ("CharControl", "CharControl", "CharControl"),
            ("Cloth", "Cloth", "Cloth"),
            ("Cloth_Leather", "Cloth_Leather", "Cloth_Leather"),
            ("Conveyer", "Conveyer", "Conveyer"),
            ("Glass", "Glass", "Glass"),
            ("Grass", "Grass", "Grass"),
            ("Grass_Leaf", "Grass_Leaf", "Grass_Leaf"),
            ("Grass_Long", "Grass_Long", "Grass_Long"),
            ("Grudge", "Grudge", "Grudge"),
            ("GuardianFoot", "GuardianFoot", "GuardianFoot"),
            ("Ice", "Ice", "Ice"),
            ("Ice_Hard", "Ice_Hard", "Ice_Hard"),
            ("LaunchPad", "LaunchPad", "LaunchPad"),
            ("Lava", "Lava", "Lava"),
            ("MagicBall", "MagicBall", "MagicBall"),
            ("Meat", "Meat", "Meat"),
            ("Metal", "Metal", "Metal"),
            ("Metal_Heavy", "Metal_Heavy", "Metal_Heavy"),
            ("Metal_Light", "Metal_Light", "Metal_Light"),
            ("Misc", "Misc", "Misc"),
            ("PriestWall", "PriestWall", "PriestWall"),
            ("Ragdoll", "Ragdoll", "Ragdoll"),
            ("Rope", "Rope", "Rope"),
            ("Snow", "Snow", "Snow"),
            ("Soil", "Soil", "Soil"),
            ("Stone", "Stone", "Stone"),
            ("Stone_DgnHeavy", "Stone_DgnHeavy", "Stone_DgnHeavy"),
            ("Stone_DgnLight", "Stone_DgnLight", "Stone_DgnLight"),
            ("Stone_Heavy", "Stone_Heavy", "Stone_Heavy"),
            ("Stone_Light", "Stone_Light", "Stone_Light"),
            ("Stone_Marble", "Stone_Marble", "Stone_Marble"),
            ("Surfing", "Surfing", "Surfing"),
            ("Undefined", "Undefined", "Undefined"),
            ("Vegetable", "Vegetable", "Vegetable"),
            ("Water", "Water", "Water"),
            ("WireNet", "WireNet", "WireNet"),
            ("Wood", "Wood", "Wood"),
            ("Wood_Thick", "Wood_Thick", "Wood_Thick"),
            ("Wood_Thin", "Wood_Thin", "Wood_Thin"),
        ),
        default="Metal_Heavy",
    )

    wall_code: EnumProperty(
        name="Wall Code",
        description="Wall code of the object",
        items=(
            ("Dummy", "Dummy", "Dummy"),
            ("Hang", "Hang", "Hang"),
            ("NoClimb", "NoClimb", "NoClimb"),
            ("NoDashUpAndNoClimb", "NoDashUpAndNoClimb", "NoDashUpAndNoClimb"),
            ("None", "None", "None"),
        ),
        default="NoClimb",
    )

    floor_code: EnumProperty(
        name="Floor Code",
        description="Floor code of the object",
        items=(
            ("Attach", "Attach", "Attach"),
            ("Dummy", "Dummy", "Dummy"),
            ("FlowRight", "FlowRight", "FlowRight"),
            ("FlowStraight", "FlowStraight", "FlowStraight"),
            ("NarrowPlace", "NarrowPlace", "NarrowPlace"),
            ("NoImpulseUpperMove", "NoImpulseUpperMove", "NoImpulseUpperMove"),
            ("None", "None", "None"),
            ("NoPreventFall", "NoPreventFall", "NoPreventFall"),
            ("Return", "Return", "Return"),
            ("Slip", "Slip", "Slip"),
        ),
        default="None",
    )

    def execute(self, context):
        try:
            selected_objs = bpy.context.selected_objects
            for obj in selected_objs:
                obj["botw_material"] = self.material
                obj["botw_sub_material"] = self.sub_material
                obj["botw_wall_code"] = self.wall_code
                obj["botw_floor_code"] = self.floor_code
            return {"FINISHED"}
        except Exception as e:
            print(e)
            ShowMessageBox("[MATERIAL ERROR]", f"{e}")
            return {"CANCELLED"}

    def invoke(self, context, event):
        wm = context.window_manager
        return wm.invoke_props_dialog(self, width=400)

    def draw(self, context):
        layout = self.layout
        col = layout.column()
        col.prop(self, "material")
        col.prop(self, "sub_material")
        col.prop(self, "wall_code")
        col.prop(self, "floor_code")


class ImportPhysics(Operator, ImportHelper):
    """Import BotW Physics File"""

    bl_idname = "botw.import_physics_yml"
    bl_label = "Import BotW physics file (.yml)"
    filename_ext = ".yml"

    filter_glob: StringProperty(default="*.yml", options={"HIDDEN"})

    def execute(self, context):
        return parse_physics(context, self.filepath)


class ExportPhysics(Operator, ExportHelper):
    """Export BotW Physics File"""

    bl_idname = "botw.export_physics_yml"
    bl_label = "Export BotW physics file (.physics.yml)"
    filename_ext = ".physics.yml"

    filter_glob: StringProperty(default="*.physics.yml", options={"HIDDEN"})

    physics_type: EnumProperty(
        name="Actor type",
        description="Select actor type. Depending on what you select, a different file will be generated.",
        items=(
            (
                "FIXED",
                "Static/Structure",
                "Static actor type (for buildings, static objects)",
            ),
            ("DYNAMIC", "Dynamic/Object", "Dynamic actor type (for moving actors)"),
            ("WEAPON", "Weapon", "Weapon actor type (for swords)"),
        ),
        default="FIXED",
    )

    vhacd: BoolProperty(
        name="Use V-HACD",
        description="Auto-generate collision using V-HACD (Disable if generated manually)",
        default=True,
    )

    remove_hulls_after_export: BoolProperty(
        name="Remove hulls after export",
        description="Remove convex hulls generated by V-HACD after exporting the physics file (doesn't matter if you don't use V-HACD)",
        default=True,
    )

    # pre-process options
    remove_doubles: BoolProperty(
        name="Remove Doubles",
        description="Collapse overlapping vertices in generated mesh",
        default=True,
    )

    apply_transforms: EnumProperty(
        name="Apply",
        description="Apply Transformations to generated mesh",
        items=(
            (
                "LRS",
                "Location + Rotation + Scale",
                "Apply location, rotation and scale",
            ),
            ("RS", "Rotation + Scale", "Apply rotation and scale"),
            ("S", "Scale", "Apply scale only"),
            ("NONE", "None", "Do not apply transformations"),
        ),
        default="NONE",
    )

    # VHACD parameters
    resolution: IntProperty(
        name="Voxel Resolution",
        description="Maximum number of voxels generated during the voxelization stage",
        default=100000,
        min=10000,
        max=64000000,
    )

    depth: IntProperty(
        name="Clipping Depth",
        description='Maximum number of clipping stages. During each split stage, all the model parts (with a concavity higher than the user defined threshold) are clipped according the "best" clipping plane',
        default=20,
        min=1,
        max=32,
    )

    concavity: FloatProperty(
        name="Maximum Concavity",
        description="Maximum concavity",
        default=0.0025,
        min=0.0,
        max=1.0,
        precision=4,
    )

    planeDownsampling: IntProperty(
        name="Plane Downsampling",
        description='Granularity of the search for the "best" clipping plane',
        default=4,
        min=1,
        max=16,
    )

    convexhullDownsampling: IntProperty(
        name="Convex Hull Downsampling",
        description="Precision of the convex-hull generation process during the clipping plane selection stage",
        default=4,
        min=1,
        max=16,
    )

    alpha: FloatProperty(
        name="Alpha",
        description="Bias toward clipping along symmetry planes",
        default=0.05,
        min=0.0,
        max=1.0,
        precision=4,
    )

    beta: FloatProperty(
        name="Beta",
        description="Bias toward clipping along revolution axes",
        default=0.05,
        min=0.0,
        max=1.0,
        precision=4,
    )

    gamma: FloatProperty(
        name="Gamma",
        description="Maximum allowed concavity during the merge stage",
        default=0.00125,
        min=0.0,
        max=1.0,
        precision=5,
    )

    pca: BoolProperty(
        name="PCA",
        description="Enable/disable normalizing the mesh before applying the convex decomposition",
        default=False,
    )

    mode: EnumProperty(
        name="ACD Mode",
        description="Approximate convex decomposition mode",
        items=(
            ("VOXEL", "Voxel", "Voxel ACD Mode"),
            ("TETRAHEDRON", "Tetrahedron", "Tetrahedron ACD Mode"),
        ),
        default="VOXEL",
    )

    maxNumVerticesPerCH: IntProperty(
        name="Maximum Vertices Per CH",
        description="Maximum number of vertices per convex-hull",
        default=32,
        min=4,
        max=1024,
    )

    minVolumePerCH: FloatProperty(
        name="Minimum Volume Per CH",
        description="Minimum volume to add vertices to convex-hulls",
        default=0.0001,
        min=0.0,
        max=0.01,
        precision=5,
    )

    def execute(self, context):
        return generate_physics(
            context,
            self.filepath,
            physics_type=self.physics_type,
            vhacd=self.vhacd,
            remove_hulls_after_export=self.remove_hulls_after_export,
            vhacd_params=[
                self.remove_doubles,
                self.apply_transforms,
                self.resolution,
                self.depth,
                self.concavity,
                self.planeDownsampling,
                self.convexhullDownsampling,
                self.alpha,
                self.beta,
                self.gamma,
                self.pca,
                self.mode,
                self.maxNumVerticesPerCH,
                self.minVolumePerCH,
            ],
        )

    def draw(self, context):
        layout = self.layout

        col = layout.column()
        col.label(text="Physics Options:")
        col.prop(self, "physics_type")
        col.prop(self, "vhacd")

        layout.separator()
        col = layout.column()
        col.label(text="Pre-Processing Options:")
        col.prop(self, "remove_hulls_after_export")
        col.prop(self, "remove_doubles")
        col.prop(self, "apply_transforms")

        layout.separator()
        col = layout.column()
        col.label(text="V-HACD Parameters:")
        col.prop(self, "resolution")
        col.prop(self, "depth")
        col.prop(self, "concavity")
        col.prop(self, "planeDownsampling")
        col.prop(self, "convexhullDownsampling")
        row = col.row()
        row.prop(self, "alpha")
        row.prop(self, "beta")
        row.prop(self, "gamma")
        col.prop(self, "pca")
        col.prop(self, "mode")
        col.prop(self, "maxNumVerticesPerCH")
        col.prop(self, "minVolumePerCH")


class ExportPhysicsBinary(Operator, ExportHelper):
    """Export BotW Binary Physics File"""

    bl_idname = "botw.export_physics_bphysics"
    bl_label = "Export BotW binary physics file (.bphysics)"
    filename_ext = ".bphysics"

    filter_glob: StringProperty(default="*.bphysics", options={"HIDDEN"})

    physics_type: EnumProperty(
        name="Actor type",
        description="Select actor type. Depending on what you select, a different file will be generated.",
        items=(
            (
                "FIXED",
                "Static/Structure",
                "Static actor type (for buildings, static objects)",
            ),
            ("DYNAMIC", "Dynamic/Object", "Dynamic actor type (for moving actors)"),
            ("WEAPON", "Weapon", "Weapon actor type (for swords)"),
        ),
        default="FIXED",
    )

    vhacd: BoolProperty(
        name="Use V-HACD",
        description="Auto-generate collision using V-HACD (Disable if generated manually)",
        default=True,
    )

    remove_hulls_after_export: BoolProperty(
        name="Remove hulls after export",
        description="Remove convex hulls generated by V-HACD after exporting the physics file (doesn't matter if you don't use V-HACD)",
        default=True,
    )

    # pre-process options
    remove_doubles: BoolProperty(
        name="Remove Doubles",
        description="Collapse overlapping vertices in generated mesh",
        default=True,
    )

    apply_transforms: EnumProperty(
        name="Apply",
        description="Apply Transformations to generated mesh",
        items=(
            (
                "LRS",
                "Location + Rotation + Scale",
                "Apply location, rotation and scale",
            ),
            ("RS", "Rotation + Scale", "Apply rotation and scale"),
            ("S", "Scale", "Apply scale only"),
            ("NONE", "None", "Do not apply transformations"),
        ),
        default="NONE",
    )

    # VHACD parameters
    resolution: IntProperty(
        name="Voxel Resolution",
        description="Maximum number of voxels generated during the voxelization stage",
        default=100000,
        min=10000,
        max=64000000,
    )

    depth: IntProperty(
        name="Clipping Depth",
        description='Maximum number of clipping stages. During each split stage, all the model parts (with a concavity higher than the user defined threshold) are clipped according the "best" clipping plane',
        default=20,
        min=1,
        max=32,
    )

    concavity: FloatProperty(
        name="Maximum Concavity",
        description="Maximum concavity",
        default=0.0025,
        min=0.0,
        max=1.0,
        precision=4,
    )

    planeDownsampling: IntProperty(
        name="Plane Downsampling",
        description='Granularity of the search for the "best" clipping plane',
        default=4,
        min=1,
        max=16,
    )

    convexhullDownsampling: IntProperty(
        name="Convex Hull Downsampling",
        description="Precision of the convex-hull generation process during the clipping plane selection stage",
        default=4,
        min=1,
        max=16,
    )

    alpha: FloatProperty(
        name="Alpha",
        description="Bias toward clipping along symmetry planes",
        default=0.05,
        min=0.0,
        max=1.0,
        precision=4,
    )

    beta: FloatProperty(
        name="Beta",
        description="Bias toward clipping along revolution axes",
        default=0.05,
        min=0.0,
        max=1.0,
        precision=4,
    )

    gamma: FloatProperty(
        name="Gamma",
        description="Maximum allowed concavity during the merge stage",
        default=0.00125,
        min=0.0,
        max=1.0,
        precision=5,
    )

    pca: BoolProperty(
        name="PCA",
        description="Enable/disable normalizing the mesh before applying the convex decomposition",
        default=False,
    )

    mode: EnumProperty(
        name="ACD Mode",
        description="Approximate convex decomposition mode",
        items=(
            ("VOXEL", "Voxel", "Voxel ACD Mode"),
            ("TETRAHEDRON", "Tetrahedron", "Tetrahedron ACD Mode"),
        ),
        default="VOXEL",
    )

    maxNumVerticesPerCH: IntProperty(
        name="Maximum Vertices Per CH",
        description="Maximum number of vertices per convex-hull",
        default=32,
        min=4,
        max=1024,
    )

    minVolumePerCH: FloatProperty(
        name="Minimum Volume Per CH",
        description="Minimum volume to add vertices to convex-hulls",
        default=0.0001,
        min=0.0,
        max=0.01,
        precision=5,
    )

    def execute(self, context):
        return generate_physics(
            context,
            self.filepath,
            binary=True,
            physics_type=self.physics_type,
            vhacd=self.vhacd,
            remove_hulls_after_export=self.remove_hulls_after_export,
            vhacd_params=[
                self.remove_doubles,
                self.apply_transforms,
                self.resolution,
                self.depth,
                self.concavity,
                self.planeDownsampling,
                self.convexhullDownsampling,
                self.alpha,
                self.beta,
                self.gamma,
                self.pca,
                self.mode,
                self.maxNumVerticesPerCH,
                self.minVolumePerCH,
            ],
        )

    def draw(self, context):
        layout = self.layout

        col = layout.column()
        col.label(text="Physics Options:")
        col.prop(self, "physics_type")
        col.prop(self, "vhacd")

        layout.separator()
        col = layout.column()
        col.label(text="Pre-Processing Options:")
        col.prop(self, "remove_hulls_after_export")
        col.prop(self, "remove_doubles")
        col.prop(self, "apply_transforms")

        layout.separator()
        col = layout.column()
        col.label(text="V-HACD Parameters:")
        col.prop(self, "resolution")
        col.prop(self, "depth")
        col.prop(self, "concavity")
        col.prop(self, "planeDownsampling")
        col.prop(self, "convexhullDownsampling")
        row = col.row()
        row.prop(self, "alpha")
        row.prop(self, "beta")
        row.prop(self, "gamma")
        col.prop(self, "pca")
        col.prop(self, "mode")
        col.prop(self, "maxNumVerticesPerCH")
        col.prop(self, "minVolumePerCH")


def MenuImport(self, context):
    self.layout.operator(ImportPhysics.bl_idname, text="BotW Physics File (.yml)")


def MenuExport(self, context):
    self.layout.operator(
        ExportPhysics.bl_idname, text="BotW Physics File (.physics.yml)"
    )
    self.layout.operator(
        ExportPhysicsBinary.bl_idname, text="BotW Binary Physics File (.bphysics)"
    )


def register():
    bpy.utils.register_class(SelectParams)
    bpy.utils.register_class(ImportPhysics)
    bpy.utils.register_class(ExportPhysics)
    bpy.utils.register_class(ExportPhysicsBinary)
    bpy.types.TOPBAR_MT_file_import.append(MenuImport)
    bpy.types.TOPBAR_MT_file_export.append(MenuExport)


def unregister():
    bpy.utils.unregister_class(SelectParams)
    bpy.utils.unregister_class(ImportPhysics)
    bpy.utils.unregister_class(ExportPhysics)
    bpy.utils.unregister_class(ExportPhysicsBinary)
    bpy.types.TOPBAR_MT_file_import.remove(MenuImport)
    bpy.types.TOPBAR_MT_file_export.remove(MenuExport)
