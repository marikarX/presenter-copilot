"""Grounded provider plans resolve targets and preconditions inside Core."""

from __future__ import annotations

import copy
import json
from dataclasses import asdict, replace
from typing import Any, cast

from presenter_core.errors import CoreDomainError, invalid_request, reject_unknown_fields
from presenter_core.presentation.creation import PresentationCreationService
from presenter_core.presentation.edit_plans import PresentationEditPlanService
from presenter_core.presentation.editing import PresentationEditService
from presenter_core.presentation.fidelity import FidelityDocument, inspect_pptx_snapshot
from presenter_core.providers.context import ProviderContextBuilder
from presenter_core.providers.execution import ProviderExecutionService
from presenter_core.providers.models import ProviderError, validate_provider_output
from presenter_core.providers.router import ReasoningRoute, ReasoningRouter
from presenter_core.providers.service import ProviderService
from presenter_core.storage.service import StorageManager

TASK_TYPE = "presentation_edit_plan"


class PresentationEditPlanningService:
    def __init__(
        self,
        storage: StorageManager,
        edits: PresentationEditService,
        plans: PresentationEditPlanService,
        providers: ProviderService,
        context: ProviderContextBuilder,
        execution: ProviderExecutionService,
    ) -> None:
        self._storage, self._edits, self._plans = storage, edits, plans
        self._providers, self._context, self._execution = providers, context, execution

    def propose(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(
            params,
            {
                "project_id",
                "document_id",
                "expected_revision_id",
                "instruction",
                "slide_numbers",
                "asset_ids",
                "previous_plan_id",
            },
        )
        project_id, document_id, revision_id = self._plans._scope(params)
        instruction = PresentationCreationService._text(
            params.get("instruction"), "instruction", 500
        )
        baseline = self._read(self._edits, project_id, document_id, revision_id)
        prior = None
        if "previous_plan_id" in params:
            _, previous = self._plans._get(
                {
                    "project_id": project_id,
                    "document_id": document_id,
                    "plan_id": params["previous_plan_id"],
                }
            )
            self._plans._current(previous)
            if previous.baseline_revision_id != revision_id or previous.planner_draft is None:
                raise invalid_request("Choose a current Copilot proposal to refine.")
            prior = copy.deepcopy(previous.planner_draft)
        asset_ids = params.get("asset_ids", [])
        if (
            not isinstance(asset_ids, list)
            or len(asset_ids) > 8
            or any(not isinstance(value, str) for value in asset_ids)
            or len(set(asset_ids)) != len(asset_ids)
        ):
            raise invalid_request("Attach at most eight unique deck pictures.")
        from presenter_core.presentation.project_assets import ProjectPictureAssetService

        library = ProjectPictureAssetService(self._storage, self._edits)
        assets = {}
        for asset_id in asset_ids:
            try:
                assets[asset_id] = library.read_picture(
                    {"project_id": project_id, "asset_id": asset_id}
                )
            except CoreDomainError as error:
                if error.code != "PROJECT_ASSET_NOT_FOUND":
                    raise
                assets[asset_id] = self._edits.read_picture_asset(
                    {
                        "project_id": project_id,
                        "document_id": document_id,
                        "expected_revision_id": revision_id,
                        "asset_id": asset_id,
                    }
                )
        if sum(item["byte_size"] for item in assets.values()) > 16 * 1024 * 1024:
            raise invalid_request("Attached deck pictures must total no more than 16 MiB.")
        numbers = params.get("slide_numbers")
        if numbers is None:
            numbers = [slide.ordinal for slide in baseline.slides]
        if (
            not isinstance(numbers, list)
            or not numbers
            or any(type(number) is not int for number in numbers)
            or len(set(numbers)) != len(numbers)
        ):
            raise invalid_request(
                "Choose a nonempty list of unique slide numbers.", field="slide_numbers"
            )
        selected = [slide for slide in baseline.slides if slide.ordinal in numbers]
        if len(selected) != len(numbers):
            raise invalid_request("A selected slide is unavailable.", field="slide_numbers")
        if prior is not None and (
            sorted(numbers) != prior["slide_numbers"] or sorted(asset_ids) != prior["asset_ids"]
        ):
            raise invalid_request(
                "Keep the proposal's slide scope and attached pictures to refine it."
            )
        allowed_slides = {slide.slide_id for slide in selected}
        allowed_objects = {
            (slide.slide_id, obj.object_id) for slide in selected for obj in slide.objects
        }
        all_slides = {slide.slide_id for slide in baseline.slides}
        all_objects = {
            (slide.slide_id, obj.object_id) for slide in baseline.slides for obj in slide.objects
        }
        diagram_context = self._diagram_context(
            self._edits, project_id, document_id, revision_id, selected
        )
        data_context = self._data_context(
            self._edits, project_id, document_id, revision_id, selected
        )
        animation_context = self._animation_context(
            self._edits, project_id, document_id, revision_id, selected
        )
        snapshot = {
            "slide_width_emu": baseline.slide_width_emu,
            "slide_height_emu": baseline.slide_height_emu,
            "ordered_slide_ids": [slide.slide_id for slide in baseline.slides],
            # Diagram and data contexts stay verbatim: providers echo them in proposals.
            "slides": [
                {
                    **self._slide_context(slide),
                    **_animations(animation_context[slide.slide_id]),
                    "diagrams": [
                        {k: v for k, v in item.items() if k != "fingerprint"}
                        for item in diagram_context.get(slide.slide_id, [])
                    ],
                    **{
                        kind: [
                            _compact_cell_styles(
                                {k: v for k, v in item.items() if k != "fingerprint"}
                            )
                            for item in items
                        ]
                        for kind, items in data_context[slide.slide_id].items()
                    },
                }
                for slide in selected
            ],
            "assets": [
                {
                    key: item[key]
                    for key in (
                        "asset_id",
                        "name",
                        "mime_type",
                        "byte_size",
                        "sha256",
                        "width",
                        "height",
                    )
                }
                for item in assets.values()
            ],
        }
        if prior is not None:
            snapshot["previous_proposal"] = {
                key: value
                for key, value in prior.items()
                if key not in {"slide_numbers", "asset_ids"}
            }
        with self._storage.project_database(project_id) as connection:
            project = connection.execute(
                "SELECT privacy_mode, remote_reasoning_acknowledged_at FROM project WHERE id = ?",
                (project_id,),
            ).fetchone()
        if project is None:
            raise CoreDomainError("PROJECT_NOT_FOUND", "Project was not found.")
        provider, health = self._providers.current_provider_and_health()
        privacy_mode = str(project["privacy_mode"])
        route = ReasoningRouter().decide(
            task_type=TASK_TYPE,
            privacy_mode=privacy_mode,
            remote_acknowledged=project["remote_reasoning_acknowledged_at"] is not None,
            provider=provider,
            provider_health=health,
        )
        if route.route == ReasoningRoute.RETRIEVAL_ONLY or provider is None:
            codes = {
                "local_only": "PRIVACY_LOCAL_ONLY_REMOTE_BLOCKED",
                "remote_reasoning_acknowledgement_required": "PRIVACY_REMOTE_ACK_REQUIRED",
                "provider_task_unsupported": "PROVIDER_TASK_UNSUPPORTED",
            }
            raise CoreDomainError(
                codes.get(route.reason, "PROVIDER_UNCONFIGURED"),
                "Configure an allowed, ready reasoning provider in Settings to propose edits.",
            )
        request, _manifest = self._context.build(
            project_id=project_id,
            task_type=TASK_TYPE,
            question=instruction,
            user_input=None,
            privacy_mode=privacy_mode,
            style_policy="preserve_voice",
            provider_id=provider.id,
            allow_private=False,
            presentation_revision_id=revision_id,
            retrieval_query=instruction,
            latency_budget_ms=30_000,
            presentation_edit_snapshot=snapshot,
        )
        request = replace(
            request,
            source_ids=(document_id,),
            presentation_revision_ids=(revision_id,),
            context_manifest={},
        )
        if request.question != instruction:
            raise CoreDomainError(
                "PRESENTATION_PLAN_CONTEXT_TOO_LARGE", "Shorten the edit request."
            )
        supplied = {
            str(item["evidence_id"]): item
            for item in (*request.evidence, *request.preferred_user_explanations)
            if isinstance(item.get("evidence_id"), str)
        }
        prepared: dict[str, Any] | None = None
        run_id: str | None = None
        previous_data: list[dict[str, Any]] = []

        def assert_current() -> None:
            current = self._edits._current_revision_source(project_id, document_id)
            if current["revision_id"] != revision_id or current["sha256"] != baseline.source_sha256:
                raise self._edits._revision_conflict()
            if prior is not None:
                self._plans._get(
                    {
                        "project_id": project_id,
                        "document_id": document_id,
                        "plan_id": params["previous_plan_id"],
                    }
                )

        def before(run: str, _manifest: dict[str, Any]) -> None:
            nonlocal run_id
            assert_current()
            run_id = run

        def bind(
            editor: PresentationEditService, kind: str, values: dict[str, Any]
        ) -> dict[str, Any]:
            if kind == "reorder_slides":
                if allowed_slides != all_slides:
                    raise invalid_request(
                        "Slide reordering requires selecting the entire presentation."
                    )
            else:
                if (
                    values.get("slide_id") in all_slides
                    and values.get("slide_id") not in allowed_slides
                ):
                    raise invalid_request(
                        "The proposed edit targets a slide outside your selection."
                    )
                if (
                    "object_id" in values
                    and (values["slide_id"], values["object_id"]) in all_objects
                    and (values["slide_id"], values["object_id"]) not in allowed_objects
                ):
                    raise invalid_request(
                        "The proposed edit targets an object outside your selection."
                    )
                if "layout_source_slide_id" in values and values["layout_source_slide_id"] not in {
                    slide.slide_id
                    for slide in self._read(editor, project_id, document_id, revision_id).slides
                }:
                    raise invalid_request("The proposed layout was not supplied.")
            if kind == "create_picture":
                asset = assets.get(values.get("asset_id"))
                if asset is None:
                    raise invalid_request("The proposed picture was not attached to this request.")
                values = {key: value for key, value in values.items() if key != "asset_id"}
                values["image_base64"] = asset["image_base64"]
            review: dict[str, Any] = {}
            bound = self._bind(
                editor, project_id, document_id, revision_id, kind, values, review_before=review
            )
            previous_data.append(review)
            return bound

        def validate(output: dict[str, Any]) -> dict[str, Any]:
            nonlocal prepared
            checked = validate_provider_output(TASK_TYPE, output)
            if any(
                evidence_id not in supplied
                for item in checked["operations"]
                for evidence_id in item["evidence_ids"]
            ):
                raise ProviderError(
                    "PROVIDER_MALFORMED_OUTPUT",
                    "The edit plan cites evidence that was not supplied.",
                )
            assert_current()
            prepared = self._plans.prepare(
                {
                    "project_id": project_id,
                    "document_id": document_id,
                    "expected_revision_id": revision_id,
                    "summary": checked["summary"],
                    "operations": [
                        {"type": item["type"], "params": item["params"]}
                        for item in checked["operations"]
                    ],
                },
                resolve_operation=bind,
                provider_run_id=run_id,
                operation_evidence=tuple(
                    tuple(item["evidence_ids"]) for item in checked["operations"]
                ),
            )
            return checked

        try:
            result = self._execution.execute(
                project_id=project_id,
                session_id=None,
                provider=provider,
                request=request,
                before_provider=before,
                output_validator=validate,
            )
            assert_current()
            if prepared is None:
                raise CoreDomainError(
                    "PRESENTATION_EDIT_PLAN_NOT_FOUND", "The proposed edits are unavailable."
                )
            prepared = {
                **prepared,
                "operations": [
                    {
                        **operation,
                        "params": {
                            **{
                                key: value
                                for key, value in operation["params"].items()
                                if key != "image_base64"
                            },
                            **(
                                {"asset_id": proposed["params"]["asset_id"]}
                                if operation["type"] == "create_picture"
                                else {}
                            ),
                        },
                    }
                    for operation, proposed in zip(
                        prepared["operations"], result.result.output["operations"], strict=True
                    )
                ],
            }
            _, retained = self._plans._get(
                {
                    "project_id": project_id,
                    "document_id": document_id,
                    "plan_id": prepared["plan_id"],
                }
            )
            retained.planner_draft = {
                "original_instruction": prior["original_instruction"] if prior else instruction,
                "latest_instruction": instruction,
                "proposal": copy.deepcopy(result.result.output),
                "slide_numbers": sorted(numbers),
                "asset_ids": sorted(asset_ids),
            }
            return {
                **prepared,
                "provider_run_id": result.provider_run_id,
                "provider_id": provider.id,
                "model_id": provider.model_id,
                "attached_assets": snapshot["assets"],
                "slide_takeaways": json.loads(request.current_slide_summary or "{}").get(
                    "slide_takeaways"
                ),
                "presentation_narrative": json.loads(request.current_slide_summary or "{}").get(
                    "presentation_narrative"
                ),
                "reviewed_claim_context": json.loads(request.current_slide_summary or "{}").get(
                    "reviewed_claim_context"
                ),
                "review_operations": [
                    {
                        **operation,
                        "rationale": proposed["rationale"],
                        "evidence_ids": proposed["evidence_ids"],
                        **({"previous_data": previous_data[index]} if previous_data[index] else {}),
                    }
                    for index, (operation, proposed) in enumerate(
                        zip(prepared["operations"], result.result.output["operations"], strict=True)
                    )
                ],
                "target_slides": [
                    {"slide_id": slide.slide_id, "ordinal": slide.ordinal} for slide in selected
                ],
                "baseline_slides": [
                    {"slide_id": slide.slide_id, "ordinal": slide.ordinal}
                    for slide in baseline.slides
                ],
                "evidence": [
                    {
                        "evidence_id": key,
                        "text": item.get("text", ""),
                        "source_locator": item.get("source_locator"),
                    }
                    for key, item in supplied.items()
                ],
            }
        except Exception:
            if prepared is not None:
                try:
                    self._plans.reject(
                        {
                            "project_id": project_id,
                            "document_id": document_id,
                            "plan_id": prepared["plan_id"],
                        }
                    )
                except CoreDomainError:
                    pass
            raise

    def _read(
        self, editor: PresentationEditService, project: str, document: str, revision: str
    ) -> FidelityDocument:
        source = editor._current_revision_source(project, document)
        if source["revision_id"] != revision:
            raise editor._revision_conflict()
        path = self._storage.paths.snapshot_path(
            project, source["local_snapshot_path"], require_exists=True
        )
        with path.open("rb") as handle:
            return inspect_pptx_snapshot(
                handle,
                document_id=document,
                expected_sha256=source["sha256"],
                byte_size=source["byte_size"],
            )

    def _diagram_context(
        self,
        editor: PresentationEditService,
        project: str,
        document: str,
        revision: str,
        slides: list[Any],
        target_id: str | None = None,
    ) -> dict[str, list[dict[str, Any]]]:
        from presenter_core.presentation.diagrams import external_dependencies, inspect_diagram
        from presenter_core.presentation.editing import _verified_source_archive
        from presenter_core.presentation.fidelity import _NS, _parse_xml_part

        source = editor._current_revision_source(project, document)
        if source["revision_id"] != revision:
            raise editor._revision_conflict()
        path = self._storage.paths.snapshot_path(
            project, source["local_snapshot_path"], require_exists=True
        )
        result = {}
        with _verified_source_archive(
            path, expected_sha256=source["sha256"], expected_byte_size=source["byte_size"]
        ) as archive:
            for slide in slides:
                root = _parse_xml_part(archive, archive.getinfo(slide.part_name))
                items = []
                for group in root.findall("p:cSld/p:spTree/p:grpSp", _NS):
                    if target_id is not None:
                        native_id = group.find("p:nvGrpSpPr/p:cNvPr", _NS).get("id")
                        if not any(
                            obj.object_id == target_id and obj.ooxml_id == native_id
                            for obj in slide.objects
                        ):
                            continue
                    info = inspect_diagram(group)
                    if info is None:
                        continue
                    native_id = group.find("p:nvGrpSpPr/p:cNvPr", _NS).get("id")
                    obj = next(v for v in slide.objects if v.ooxml_id == native_id)
                    if external_dependencies(root, group):
                        info = {
                            **info,
                            "editable": False,
                            "reason": "External dependencies are preserved.",
                        }
                    items.append(
                        {
                            "object_id": obj.object_id,
                            "name": obj.name,
                            **{k: v for k, v in info.items() if not k.startswith("_")},
                        }
                    )
                    if len(items) == 20:
                        break
                result[slide.slide_id] = items
        return result

    def _animation_context(
        self,
        editor: PresentationEditService,
        project: str,
        document: str,
        revision: str,
        slides: list[Any],
    ) -> dict[str, dict[str, Any]]:
        from presenter_core.presentation.editing import _verified_source_archive
        from presenter_core.presentation.fidelity import _parse_xml_part
        from presenter_core.presentation.slide_animations import slide_animation_state

        source = editor._current_revision_source(project, document)
        if source["revision_id"] != revision:
            raise editor._revision_conflict()
        path = self._storage.paths.snapshot_path(
            project, source["local_snapshot_path"], require_exists=True
        )
        with _verified_source_archive(
            path, expected_sha256=source["sha256"], expected_byte_size=source["byte_size"]
        ) as archive:
            return {
                slide.slide_id: slide_animation_state(
                    _parse_xml_part(archive, archive.getinfo(slide.part_name)), slide
                )
                for slide in slides
            }

    def _data_context(
        self,
        editor: PresentationEditService,
        project: str,
        document: str,
        revision: str,
        slides: list[Any],
        target_id: str | None = None,
    ) -> dict[str, dict[str, list[dict[str, Any]]]]:
        from presenter_core.presentation.chart_editing import inspect_chart
        from presenter_core.presentation.editing import _verified_source_archive
        from presenter_core.presentation.fidelity import _NS, _parse_xml_part
        from presenter_core.presentation.tables import inspect_table

        source = editor._current_revision_source(project, document)
        if source["revision_id"] != revision:
            raise editor._revision_conflict()
        path = self._storage.paths.snapshot_path(
            project, source["local_snapshot_path"], require_exists=True
        )
        result = {}
        with _verified_source_archive(
            path, expected_sha256=source["sha256"], expected_byte_size=source["byte_size"]
        ) as archive:
            for slide in slides:
                root = _parse_xml_part(archive, archive.getinfo(slide.part_name))
                items: dict[str, list[dict[str, Any]]] = {
                    "tables": [],
                    "charts": [],
                    "text_fits": [],
                    "shape_fills": [],
                }
                for frame in root.findall("p:cSld/p:spTree/p:graphicFrame", _NS):
                    native_id = frame.find("p:nvGraphicFramePr/p:cNvPr", _NS).get("id")
                    obj = next(v for v in slide.objects if v.ooxml_id == native_id)
                    if target_id is not None and obj.object_id != target_id:
                        continue
                    table = inspect_table(frame)
                    if table is not None:
                        kind, info = "tables", table
                    else:
                        chart = inspect_chart(archive, slide.part_name, frame)
                        if chart is None:
                            continue
                        kind, info = "charts", chart[0]
                    if len(items[kind]) < 20:
                        items[kind].append({"object_id": obj.object_id, "name": obj.name, **info})
                    if target_id is not None or all(
                        len(items[k]) == 20 for k in ["tables", "charts"]
                    ):
                        break
                from presenter_core.presentation.shape_fills import inspect_fill

                for shape in root.findall("p:cSld/p:spTree/p:sp", _NS):
                    identity = shape.find("p:nvSpPr/p:cNvPr", _NS)
                    if identity is None:
                        continue
                    obj = next(v for v in slide.objects if v.ooxml_id == identity.get("id"))
                    if target_id is not None and obj.object_id != target_id:
                        continue
                    items["shape_fills"].append(
                        {"object_id": obj.object_id, "name": obj.name, **inspect_fill(shape)}
                    )
                    if target_id is not None or len(items["shape_fills"]) == 20:
                        break
                from presenter_core.presentation.text_fit_editing import inspect_fit
                from presenter_core.presentation.text_inheritance import TextInheritance

                try:
                    reader = TextInheritance(archive, slide.part_name)
                except CoreDomainError as error:
                    if error.code != "PRESENTATION_EDIT_UNSUPPORTED":
                        raise
                    # Unsupported inheritance only disables fitting on this slide;
                    # table/chart proposals retain their independent capabilities.
                    result[slide.slide_id] = items
                    continue
                for shape in reader.slide.findall("p:cSld/p:spTree/p:sp", _NS):
                    identity = shape.find("p:nvSpPr/p:cNvPr", _NS)
                    if identity is None:
                        continue
                    obj = next(v for v in slide.objects if v.ooxml_id == identity.get("id"))
                    if target_id is not None and obj.object_id != target_id:
                        continue
                    items["text_fits"].append(
                        {
                            "object_id": obj.object_id,
                            "name": obj.name,
                            **inspect_fit(reader, shape, text=obj.text),
                        }
                    )
                    if target_id is not None or len(items["text_fits"]) == 20:
                        break
                result[slide.slide_id] = items
        return result

    @staticmethod
    def _slide_context(slide: Any) -> dict[str, Any]:
        result = asdict(slide)
        result.pop("part_name")
        result.pop("ooxml_slide_id")
        if result["speaker_notes"] is not None and len(result["speaker_notes"]) > 12000:
            result["speaker_notes"] = result["speaker_notes"][:500]
            result["speaker_notes_editable"] = False
        for obj in result["objects"]:
            obj.pop("ooxml_id")
            # Present edit capabilities in the units the plan schema uses.
            rotation = obj.get("rotation")
            if rotation is not None:
                obj["rotation"] = {
                    "rotation_degrees": rotation["rotation"] / 60_000,
                    "flip_horizontal": rotation["flip_horizontal"],
                    "flip_vertical": rotation["flip_vertical"],
                }
            adjustment = obj.get("picture_adjustment")
            if adjustment is not None:
                obj["picture_adjustment"] = {
                    "brightness_percent": adjustment["brightness"],
                    "contrast_percent": adjustment["contrast"],
                    "grayscale": adjustment["grayscale"],
                }
            if len(obj["text"]) > 2000:
                obj["text"] = obj["text"][:500]
                obj["text_edit_candidate"] = False
                obj["single_run_text_edit_candidate"] = False
                obj["uniform_run_text_edit_candidate"] = False
                obj["text_format_edit_candidate"] = False
        return cast(dict[str, Any], _compact(result, drop_false=True))

    def _bind(
        self,
        editor: PresentationEditService,
        project: str,
        document: str,
        revision: str,
        kind: str,
        values: dict[str, Any],
        *,
        review_before: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        fidelity = self._read(editor, project, document, revision)
        params = copy.deepcopy(values)
        if kind == "reorder_slides":
            return params
        slide = next(
            (item for item in fidelity.slides if item.slide_id == params["slide_id"]), None
        )
        if slide is None:
            raise invalid_request("The proposed slide is no longer available in this plan.")
        if kind == "replace_speaker_notes":
            if (
                not slide.speaker_notes_editable
                or slide.speaker_notes is None
                or len(slide.speaker_notes) > 12000
            ):
                raise invalid_request("The proposed notes target is not editable.")
            params["expected_text"] = slide.speaker_notes
        if kind == "change_object_layer":
            params["expected_object_ids"] = [item.object_id for item in slide.objects]
        if kind == "set_slide_transition":
            if slide.transition is None:
                raise invalid_request("The proposed slide transition is not editable.")
            params["expected_transition"] = slide.transition
        if kind == "set_slide_hidden":
            params["expected_hidden"] = slide.hidden
        if kind == "set_slide_animations":
            animations = self._animation_context(editor, project, document, revision, [slide])
            if not animations[slide.slide_id]["editable"]:
                raise invalid_request("The proposed slide animations are not editable.")
            params["expected_fingerprint"] = animations[slide.slide_id]["fingerprint"]
        if kind == "set_slide_background":
            if slide.background is None:
                raise invalid_request("The proposed slide background is not editable.")
            params["expected_background"] = {
                "state": slide.background.state,
                "color": slide.background.color,
            }
        if kind == "group_objects":
            objects = params.get("objects")
            if not isinstance(objects, list) or not 2 <= len(objects) <= 20:
                raise invalid_request("Choose 2 to 20 supported objects to group.")
            bound = []
            seen = set()
            for target in objects:
                if not isinstance(target, dict) or set(target) != {"object_id"}:
                    raise invalid_request("Grouping selects only object identities.")
                identity = target["object_id"]
                obj = next((item for item in slide.objects if item.object_id == identity), None)
                if obj is None or not obj.group_editable or obj.geometry is None:
                    raise invalid_request("A grouping target is unavailable or unsupported.")
                if identity in seen:
                    raise invalid_request("Grouping targets must be distinct.")
                seen.add(identity)
                bound.append({"object_id": identity, "expected_geometry": asdict(obj.geometry)})
            if review_before is not None:
                review_before["group_members"] = [
                    {"object_id": item["object_id"], "name": obj.name, "text": obj.text[:2000]}
                    for item in bound
                    for obj in slide.objects
                    if obj.object_id == item["object_id"]
                ]
            params["objects"] = bound
            return params
        if "object_id" not in params:
            return params
        obj = next((item for item in slide.objects if item.object_id == params["object_id"]), None)
        if obj is None:
            raise invalid_request("The proposed object is no longer available in this plan.")
        if kind == "ungroup_object" and review_before is not None:
            review_before["group_name"] = obj.name
        if kind in {
            "replace_table_cells",
            "reshape_table",
            "format_table_cells",
            "set_table_borders",
            "merge_table_cells",
            "fit_table_rows",
            "split_table_cells",
            "replace_chart_data",
            "reshape_chart",
            "set_chart_legend",
            "set_chart_color",
            "set_chart_fill",
            "set_chart_marker",
            "set_chart_labels",
            "set_chart_axis",
        }:
            context = self._data_context(
                editor, project, document, revision, [slide], target_id=obj.object_id
            )
            collection = (
                "tables"
                if kind
                in {
                    "replace_table_cells",
                    "reshape_table",
                    "format_table_cells",
                    "set_table_borders",
                    "merge_table_cells",
                    "fit_table_rows",
                    "split_table_cells",
                }
                else "charts"
            )
            target = next(
                (v for v in context[slide.slide_id][collection] if v["object_id"] == obj.object_id),
                None,
            )
            if (
                target is None
                or not target["editable"]
                or (kind.startswith("reshape_") and not target["structure_editable"])
                or (kind == "set_chart_legend" and not target["legend"]["editable"])
            ):
                raise invalid_request(
                    "The proposed table/chart target is not editable for this operation."
                )
            if kind == "fit_table_rows":
                if not target["fit"]["editable"]:
                    raise invalid_request(target["fit"]["reason"])
                if review_before is not None:
                    review_before.update(copy.deepcopy(target["fit"]))
            if kind in {"merge_table_cells", "split_table_cells"}:
                from presenter_core.presentation.table_merge import complete_range

                complete_range(params, target["cells"], target["spans"])
                if review_before is not None:
                    review_before.update(
                        copy.deepcopy(
                            {"cells": target["cells"], "merge_regions": target["spans"]["regions"]}
                        )
                    )
            if kind == "set_table_borders":
                from presenter_core.presentation.table_borders import previous_borders

                previous = previous_borders(target["borders"], params)
                if review_before is not None:
                    review_before.update(previous)
            if kind == "format_table_cells":
                from presenter_core.presentation.table_format import previous_styles

                previous = previous_styles(target["formatting"], params)
                if review_before is not None:
                    review_before.update(previous)
            if kind == "set_chart_axis":
                if not target["axes"]["editable"]:
                    raise invalid_request("The proposed native axes are read-only.")
                previous = next(
                    v for v in target["axes"]["axes"] if v["axis_kind"] == params["axis_kind"]
                )
                if review_before is not None:
                    review_before.update(
                        copy.deepcopy({k: v for k, v in previous.items() if k != "title_editable"})
                    )
            if kind == "set_chart_labels":
                from presenter_core.presentation.chart_labels import previous_labels

                previous = previous_labels(target["labels"], params["series_index"])
                if review_before is not None:
                    review_before.update(previous)
            if kind == "set_chart_marker":
                from presenter_core.presentation.chart_markers import previous_marker

                previous = previous_marker(target["markers"], params["series_index"])
                if review_before is not None:
                    review_before.update(previous)
            if kind == "set_chart_fill":
                from presenter_core.presentation.chart_fills import previous_fill

                previous = previous_fill(
                    target["fills"], params["series_index"], params["point_index"]
                )
                if review_before is not None:
                    review_before.update(previous)
            if kind == "set_chart_color":
                from presenter_core.presentation.chart_colors import previous_color

                previous = previous_color(
                    target["colors"], params["series_index"], params["point_index"]
                )
                if review_before is not None:
                    review_before.update(previous)
            params["expected_fingerprint"] = target["fingerprint"]
            if review_before is not None and kind not in {
                "set_chart_color",
                "set_chart_fill",
                "set_chart_marker",
                "format_table_cells",
                "set_table_borders",
                "merge_table_cells",
                "fit_table_rows",
                "split_table_cells",
                "set_chart_labels",
                "set_chart_axis",
            }:
                review_before.update(
                    copy.deepcopy(
                        {"cells": target["cells"]}
                        if collection == "tables"
                        else {
                            "legend_position": target["legend"]["position"],
                            "legend_overlay": target["legend"]["overlay"],
                        }
                        if kind == "set_chart_legend"
                        else target["data"]
                    )
                )
        elif kind in {"replace_diagram", "delete_diagram"}:
            diagrams = self._diagram_context(
                editor, project, document, revision, [slide], target_id=obj.object_id
            )
            diagram = next(
                (item for item in diagrams[slide.slide_id] if item["object_id"] == obj.object_id),
                None,
            )
            if diagram is None or not diagram["editable"]:
                raise invalid_request("The proposed diagram target is not editable.")
            params["expected_fingerprint"] = diagram["fingerprint"]
        elif kind == "set_shape_fill":
            context = self._data_context(
                editor, project, document, revision, [slide], target_id=obj.object_id
            )
            target = next(
                (
                    v
                    for v in context[slide.slide_id]["shape_fills"]
                    if v["object_id"] == obj.object_id
                ),
                None,
            )
            if target is None or not target["editable"]:
                raise invalid_request("The proposed shape fill target is not editable.")
            params["expected_fingerprint"] = target["fingerprint"]
            if review_before is not None:
                review_before["fill"] = copy.deepcopy(target["fill"])
        elif kind == "fit_text_shape":
            context = self._data_context(
                editor, project, document, revision, [slide], target_id=obj.object_id
            )
            target = next(
                (
                    v
                    for v in context[slide.slide_id]["text_fits"]
                    if v["object_id"] == obj.object_id
                ),
                None,
            )
            if target is None or not target["editable"]:
                raise invalid_request("The proposed text fitting target is not editable.")
            params["expected_fingerprint"] = target["fingerprint"]
            if review_before is not None:
                review_before.update(
                    copy.deepcopy(
                        {k: target[k] for k in ["geometry_pt", "paragraphs", "cached_font_scale"]}
                    )
                )
        elif kind == "set_text_hyperlink":
            if obj.hyperlink is None:
                raise invalid_request("The proposed text link is not editable.")
            params["expected_text"] = obj.text
            params["expected_url"] = obj.hyperlink.url
            params["expected_slide_id"] = obj.hyperlink.slide_id
            if params.get("replacement_slide_id") is None:
                params.pop("replacement_slide_id", None)
            if params.get("replacement_url") is None and "replacement_slide_id" in params:
                params.pop("replacement_url", None)
        elif kind == "replace_text_shape":
            if (
                not (obj.single_run_text_edit_candidate or obj.uniform_run_text_edit_candidate)
                or len(obj.text) > 2000
            ):
                raise invalid_request("The proposed text target is not editable.")
            params.update(operation_type=kind, expected_text=obj.text)
        elif kind in {"format_text_shape", "format_shape_style"}:
            style = obj.text_style if kind == "format_text_shape" else obj.shape_style
            if style is None or not style.editable or style.fingerprint is None:
                raise invalid_request("The proposed style target is not editable.")
            params["expected_style_fingerprint"] = style.fingerprint
            params["replacement_style"] = {
                key: value
                for key, value in params["replacement_style"].items()
                if value is not None
            }
            if kind == "format_text_shape":
                params["expected_text"] = obj.text
        elif kind in {
            "transform_object",
            "delete_object",
            "duplicate_object",
            "crop_picture",
            "adjust_picture",
            "rotate_object",
            "ungroup_object",
        }:
            if obj.geometry is None:
                raise invalid_request("The proposed object has no supported geometry.")
            params["expected_geometry"] = asdict(obj.geometry)
            if kind == "crop_picture":
                if obj.picture_crop is None:
                    raise invalid_request("The proposed picture has no supported crop.")
                params["expected_crop"] = {
                    f"{key}_percent": value / 1000
                    for key, value in asdict(obj.picture_crop).items()
                }
                params["replacement_crop"] = {
                    f"{key}_percent": value / 1000
                    for key, value in params["replacement_crop"].items()
                }
            if kind == "rotate_object":
                if obj.rotation is None:
                    raise invalid_request("The proposed object cannot be rotated safely.")
                params["expected_rotation"] = {
                    "rotation_degrees": obj.rotation.rotation / 60_000,
                    "flip_horizontal": obj.rotation.flip_horizontal,
                    "flip_vertical": obj.rotation.flip_vertical,
                }
            if kind == "adjust_picture":
                if obj.picture_adjustment is None:
                    raise invalid_request("The proposed picture cannot be adjusted safely.")
                params["expected_adjustment"] = {
                    "brightness_percent": obj.picture_adjustment.brightness,
                    "contrast_percent": obj.picture_adjustment.contrast,
                    "grayscale": obj.picture_adjustment.grayscale,
                }
        return params


def _animations(state: dict[str, Any]) -> dict[str, Any]:
    """Planning view of a slide's entrance sequence; absent means read-only."""
    if not state["editable"]:
        return {}
    return {
        "animations_editable": True,
        "animations": [
            {key: effect[key] for key in ("object_id", "effect", "start")}
            for effect in state["effects"]
        ],
    }


def _compact(value: Any, *, drop_false: bool = False) -> Any:
    """Drop null fields and style fingerprints from planning context in place.

    Absent capabilities mean unavailable; Core rebinds fingerprints itself. With
    drop_false, false flags are dropped too (absent means false).
    """
    if isinstance(value, dict):
        for key in [
            k
            for k, v in value.items()
            if v is None or k == "fingerprint" or (drop_false and v is False)
        ]:
            del value[key]
        for item in value.values():
            _compact(item, drop_false=drop_false)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _compact(item, drop_false=drop_false)
    return value


def _compact_cell_styles(value: Any) -> Any:
    """Compact per-cell table styles (never echoed by providers) to bound context size."""
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "cell_styles":
                _compact(item)
            else:
                _compact_cell_styles(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _compact_cell_styles(item)
    return value
