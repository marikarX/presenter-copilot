"""Insert a video or audio file onto a slide, stored the way PowerPoint 2010+ stores
media: a picture whose nvPr names the file (a:videoFile / a:audioFile plus p14:media)
and whose image is the poster frame (the first video frame, or a speaker icon).

The file comes from a path chosen in the desktop main process; the renderer never
sees it. PyAV checks it is a format PowerPoint plays: MP4 video (H.264, HEVC or
MPEG-4) or MP3, M4A or WAV audio.
"""

from __future__ import annotations

import copy
import io
import shutil
import uuid
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

from lxml import etree  # type: ignore[import-untyped]
from PIL import Image, ImageDraw

from presenter_core.errors import CoreDomainError, invalid_request, reject_unknown_fields
from presenter_core.presentation.fidelity import (
    _NS,
    OBJECT_LIMIT,
    PACKAGE_REL_NS,
    PRESENTATION_NS,
    REL_NS,
    FidelityGeometry,
    _parse_xml_part,
    inspect_pptx_snapshot,
)
from presenter_core.presentation.graphic_duplication import CT

if TYPE_CHECKING:
    from presenter_core.presentation.editing import PresentationEditService

P = f"{{{PRESENTATION_NS}}}"
A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
R = f"{{{REL_NS}}}"
P14 = "http://schemas.microsoft.com/office/powerpoint/2010/main"
MEDIA_REL = "http://schemas.microsoft.com/office/2007/relationships/media"
MAX_MEDIA_BYTES = 512 * 1024 * 1024
MAX_SECONDS = 3 * 60 * 60
# extension -> (kind, content type, allowed codecs)
FORMATS = {
    ".mp4": ("video", "video/mp4", {"h264", "hevc", "mpeg4"}),
    ".m4v": ("video", "video/mp4", {"h264", "hevc", "mpeg4"}),
    ".mp3": ("audio", "audio/mpeg", {"mp3", "mp3float"}),
    ".m4a": ("audio", "audio/mp4", {"aac"}),
    ".wav": ("audio", "audio/wav", {"pcm_s16le", "pcm_s24le", "pcm_f32le", "pcm_u8"}),
}
EMU_PER_INCH = 914_400


def _reject(message: str) -> CoreDomainError:
    return CoreDomainError("PRESENTATION_EDIT_UNSUPPORTED", message)


def _speaker_icon() -> bytes:
    """A plain speaker glyph, like PowerPoint's audio icon."""
    image = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.polygon([(40, 96), (96, 96), (160, 40), (160, 216), (96, 160), (40, 160)], fill="#404040")
    for radius in (40, 72):
        draw.arc((160 - radius, 128 - radius, 160 + radius, 128 + radius), -50, 50, "#404040", 14)
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def probe_media(path: Path) -> dict[str, Any]:
    """Kind, duration, frame size and poster PNG of a playable media file."""
    import av

    extension = path.suffix.lower()
    if extension not in FORMATS:
        raise _reject("Choose an MP4 video or an MP3, M4A or WAV audio file.")
    kind, content_type, codecs = FORMATS[extension]
    size = path.stat().st_size
    if not 0 < size <= MAX_MEDIA_BYTES:
        raise _reject("Media files can be up to 512 MB.")
    try:
        with av.open(str(path)) as container:
            video = container.streams.video[0] if container.streams.video else None
            audio = container.streams.audio[0] if container.streams.audio else None
            seconds = container.duration / av.time_base if container.duration else 0.0
            if kind == "video":
                if video is None or video.codec_context.name not in codecs:
                    raise _reject("The video must use H.264, HEVC or MPEG-4 in an MP4 file.")
                frame = next(container.decode(video), None)
                if frame is None:
                    raise _reject("The video has no frames.")
                poster_image = frame.to_image()  # type: ignore[no-untyped-call]
                width, height = poster_image.size
                buffer = io.BytesIO()
                poster_image.convert("RGB").save(buffer, format="PNG")
                poster = buffer.getvalue()
            else:
                if video is not None or audio is None or audio.codec_context.name not in codecs:
                    raise _reject("The audio file uses a format PowerPoint may not play.")
                width = height = 256
                poster = _speaker_icon()
    except CoreDomainError:
        raise
    except Exception as error:
        raise _reject("The media file could not be read.") from error
    if not 0 < seconds <= MAX_SECONDS:
        raise _reject("Media can be up to 3 hours long.")
    return {
        "kind": kind,
        "content_type": content_type,
        "extension": extension,
        "seconds": seconds,
        "width": width,
        "height": height,
        "poster": poster,
        "byte_size": size,
    }


def insert_media(editor: PresentationEditService, params: dict[str, Any]) -> dict[str, Any]:
    from presenter_core.presentation.editing import _next_ooxml_shape_id, _verified_source_archive

    reject_unknown_fields(
        params, {"project_id", "document_id", "expected_revision_id", "slide_id", "path"}
    )
    project = editor._project_id(params.get("project_id"))
    document = editor._document_id(params.get("document_id"))
    baseline = editor._uuid_field(params.get("expected_revision_id"), "expected_revision_id")
    slide_id = editor._uuid_field(params.get("slide_id"), "slide_id")
    raw_path = params.get("path")
    if not isinstance(raw_path, str) or not raw_path or len(raw_path) > 4096:
        raise invalid_request("path must name a local media file.", field="path")
    media_path = Path(raw_path)
    if not media_path.is_absolute() or not media_path.is_file():
        raise invalid_request("path must name a local media file.", field="path")
    media = probe_media(media_path)
    current = editor._current_revision_source(project, document)
    if current["revision_id"] != baseline:
        raise editor._revision_conflict()
    snapshot = editor._storage.paths.snapshot_path(
        project, current["local_snapshot_path"], require_exists=True
    )
    with snapshot.open("rb") as handle:
        fidelity = inspect_pptx_snapshot(
            handle,
            document_id=document,
            expected_sha256=current["sha256"],
            byte_size=current["byte_size"],
        )
    slide = next((s for s in fidelity.slides if s.slide_id == slide_id), None)
    if slide is None:
        raise CoreDomainError("PRESENTATION_EDIT_TARGET_NOT_FOUND", "The slide is unavailable.")
    if fidelity.object_count >= OBJECT_LIMIT:
        raise CoreDomainError(
            "PRESENTATION_EDIT_RESOURCE_LIMIT",
            "This presentation cannot contain another object safely.",
        )
    # Video: centred, at most 60% of the slide, keeping its aspect. Audio: a 1/2" icon.
    if media["kind"] == "video":
        scale = min(
            fidelity.slide_width_emu * 0.6 / media["width"],
            fidelity.slide_height_emu * 0.6 / media["height"],
        )
        width, height = int(media["width"] * scale), int(media["height"] * scale)
    else:
        width = height = EMU_PER_INCH // 2
    geometry = FidelityGeometry(
        x_emu=(fidelity.slide_width_emu - width) // 2,
        y_emu=(fidelity.slide_height_emu - height) // 2,
        width_emu=width,
        height_emu=height,
    )
    created: list[str] = []

    def write(original: Path, destination: Path) -> None:
        created.clear()
        with _verified_source_archive(
            original, expected_sha256=current["sha256"], expected_byte_size=current["byte_size"]
        ) as archive:
            members = {info.filename: info for info in archive.infolist()}
            rels_part = editor._relationship_part_name(slide.part_name)
            root = _parse_xml_part(archive, members[slide.part_name])
            rels = (
                _parse_xml_part(archive, members[rels_part])
                if rels_part in members
                else etree.Element(
                    f"{{{PACKAGE_REL_NS}}}Relationships", nsmap={None: PACKAGE_REL_NS}
                )
            )
            types = _parse_xml_part(archive, members["[Content_Types].xml"])
            tree = root.find("p:cSld/p:spTree", _NS)
            if tree is None:
                raise _reject("This slide has no native object tree.")
            token = uuid.uuid4().hex
            media_part = f"ppt/media/copilot-media-{token}{media['extension']}"
            poster_part = f"ppt/media/copilot-poster-{token}.png"
            if media_part in members or poster_part in members:
                raise _reject("A media part name is already in use.")
            used = {item.get("Id") for item in rels}

            def relate(kind: str, part: str) -> str:
                number = 1
                while f"rIdMedia{number}" in used:
                    number += 1
                rid = f"rIdMedia{number}"
                used.add(rid)
                etree.SubElement(
                    rels,
                    f"{{{PACKAGE_REL_NS}}}Relationship",
                    Id=rid,
                    Type=kind,
                    Target="../media/" + part.rsplit("/", 1)[1],
                )
                return rid

            link = relate(f"{REL_NS}/{media['kind']}", media_part)
            embed = relate(MEDIA_REL, media_part)
            poster = relate(f"{REL_NS}/image", poster_part)
            identity = _next_ooxml_shape_id(tree)
            label = "Video" if media["kind"] == "video" else "Audio"
            existing = {n.get("name") for n in root.iter(f"{P}cNvPr")}
            number = 1
            while f"{label} {number}" in existing:
                number += 1
            name = f"{label} {number}"
            picture = etree.SubElement(tree, f"{P}pic")
            nonvisual = etree.SubElement(picture, f"{P}nvPicPr")
            native = etree.SubElement(nonvisual, f"{P}cNvPr", id=identity, name=name)
            click = etree.SubElement(native, f"{A}hlinkClick", action="ppaction://media")
            click.set(f"{R}id", "")
            locks = etree.SubElement(etree.SubElement(nonvisual, f"{P}cNvPicPr"), f"{A}picLocks")
            locks.set("noChangeAspect", "1")
            properties = etree.SubElement(nonvisual, f"{P}nvPr")
            etree.SubElement(properties, f"{A}{media['kind']}File").set(f"{R}link", link)
            extension = etree.SubElement(
                etree.SubElement(properties, f"{P}extLst"),
                f"{P}ext",
                uri="{DAA4B4D4-6D71-4841-9C94-3DE7FCFB9230}",
            )
            etree.SubElement(extension, f"{{{P14}}}media", nsmap={"p14": P14}).set(
                f"{R}embed", embed
            )
            fill = etree.SubElement(picture, f"{P}blipFill")
            etree.SubElement(fill, f"{A}blip").set(f"{R}embed", poster)
            etree.SubElement(etree.SubElement(fill, f"{A}stretch"), f"{A}fillRect")
            shape = etree.SubElement(picture, f"{P}spPr")
            transform = etree.SubElement(shape, f"{A}xfrm")
            etree.SubElement(transform, f"{A}off", x=str(geometry.x_emu), y=str(geometry.y_emu))
            etree.SubElement(
                transform, f"{A}ext", cx=str(geometry.width_emu), cy=str(geometry.height_emu)
            )
            etree.SubElement(etree.SubElement(shape, f"{A}prstGeom", prst="rect"), f"{A}avLst")
            for part, content_type in (
                (media_part, media["content_type"]),
                (poster_part, "image/png"),
            ):
                etree.SubElement(
                    types, f"{{{CT}}}Override", PartName="/" + part, ContentType=content_type
                )
            rewritten = {
                slide.part_name: etree.tostring(
                    root, encoding="UTF-8", xml_declaration=True, standalone=True
                ),
                rels_part: etree.tostring(
                    rels, encoding="UTF-8", xml_declaration=True, standalone=True
                ),
                "[Content_Types].xml": etree.tostring(
                    types, encoding="UTF-8", xml_declaration=True, standalone=True
                ),
            }
            with zipfile.ZipFile(destination, "w", allowZip64=True) as output:
                output.comment = archive.comment
                for info in archive.infolist():
                    payload = rewritten.pop(info.filename, None)
                    if payload is not None:
                        output.writestr(copy.copy(info), payload)
                    else:
                        with (
                            archive.open(info) as reader,
                            output.open(copy.copy(info), "w") as writer,
                        ):
                            shutil.copyfileobj(reader, writer, length=1024 * 1024)
                for part, payload in rewritten.items():
                    output.writestr(part, payload, compress_type=zipfile.ZIP_DEFLATED)
                output.writestr(poster_part, media["poster"])
                # Media is already compressed; store it as PowerPoint does.
                with (
                    media_path.open("rb") as reader,
                    output.open(zipfile.ZipInfo(media_part, (1980, 1, 1, 0, 0, 0)), "w") as writer,
                ):
                    shutil.copyfileobj(reader, writer, length=1024 * 1024)
        with destination.open("rb") as handle:
            updated = inspect_pptx_snapshot(
                handle,
                document_id=document,
                expected_sha256=editor._sha256_path(destination),
                byte_size=destination.stat().st_size,
            )
        before = {o.object_id: o for s in fidelity.slides for o in s.objects}
        after = {o.object_id: o for s in updated.slides for o in s.objects}
        added = [o for k, o in after.items() if k not in before]
        if (
            len(added) != 1
            or added[0].kind != "pic"
            or added[0].name != name
            or added[0].geometry != geometry
            or any(after.get(k) != v for k, v in before.items())
        ):
            raise CoreDomainError(
                "PRESENTATION_EDIT_VALIDATION_FAILED", "The inserted media did not pass validation."
            )
        created.append(added[0].object_id)

    result = editor._commit_revision(project, document, baseline, current, write)
    return {
        **result,
        "created_object_id": created[0] if created else None,
        "media_kind": media["kind"],
        "duration_seconds": round(media["seconds"], 3),
        "media_byte_size": media["byte_size"],
    }
