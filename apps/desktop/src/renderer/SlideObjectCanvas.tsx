import { useNativeLayers } from "./NativeLayers";
import { useEffect, useRef, useState } from "react";
import {
  guidedTranslation,
  guidedResize,
  type GuideTolerance,
  type AlignmentGuide,
} from "./canvas-guides";
import {
  usePowerPointAppearance,
  type NativeAppearanceTarget,
} from "./NativeAppearance";
import {
  RESIZE_HANDLES,
  type ResizeHandle,
  translationOperations,
  type LayoutGeometry,
  type LayoutObject,
} from "./object-layout";

export function SlideObjectCanvas({
  image,
  slideNumber,
  objects,
  size,
  selectedIds,
  enabled,
  onSelect,
  onMove,
  onResize,
  grid,
  alignmentGuides = false,
  nativeTarget = null,
}: {
  nativeTarget?: NativeAppearanceTarget | null;
  image: string;
  slideNumber: number;
  objects: LayoutObject[];
  size: { width: number; height: number } | null;
  selectedIds: string[];
  enabled: boolean;
  onSelect: (ids: string[]) => void;
  onMove: (
    ids: string[],
    dx: number,
    dy: number,
    tolerance?: GuideTolerance,
  ) => void;
  onResize: (
    ids: string[],
    handle: ResizeHandle,
    dx: number,
    dy: number,
    proportional: boolean,
    tolerance?: GuideTolerance,
  ) => void;
  grid: number;
  alignmentGuides?: boolean;
}) {
  const live = useNativeLayers(nativeTarget, slideNumber, enabled, objects);
  const native = usePowerPointAppearance(
    nativeTarget,
    slideNumber,
    live.stop,
    live.workerBusy,
    live.ready,
  );
  const displayImage = native.image ?? image;
  const img = useRef<HTMLImageElement>(null);
  const [box, setBox] = useState<{
    left: number;
    top: number;
    width: number;
    height: number;
  } | null>(null);
  const [drag, setDrag] = useState<{
    x: number;
    y: number;
    endX: number;
    endY: number;
    initial: string[];
  } | null>(null);
  // Double-clicking a group enters it: its members become selectable on the canvas.
  const [enteredGroup, setEnteredGroup] = useState<string | null>(null);
  const movable = objects.filter(
    (object) =>
      object.geometry_editable &&
      (!object.group_child || object.group_id === enteredGroup) &&
      object.geometry &&
      size &&
      object.geometry.x_emu >= 0 &&
      object.geometry.y_emu >= 0 &&
      object.geometry.x_emu + object.geometry.width_emu <= size.width &&
      object.geometry.y_emu + object.geometry.height_emu <= size.height,
  );
  const move = useRef<{
    x: number;
    y: number;
    clientX: number;
    clientY: number;
    ids: string[];
  } | null>(null);
  const resize = useRef<{
    x: number;
    y: number;
    clientX: number;
    clientY: number;
    ids: string[];
    handle: ResizeHandle;
  } | null>(null);
  const [ghosts, setGhosts] = useState<
    ReturnType<typeof translationOperations>
  >([]);
  const [guides, setGuides] = useState<AlignmentGuide[]>([]);
  const suppressClick = useRef(false);
  useEffect(() => {
    const node = img.current;
    if (!node) return;
    const measure = () =>
      setBox(
        node.complete &&
          node.naturalWidth &&
          node.offsetWidth > 0 &&
          node.offsetHeight > 0
          ? {
              left: node.offsetLeft,
              top: node.offsetTop,
              width: node.offsetWidth,
              height: node.offsetHeight,
            }
          : null,
      );
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(node);
    if (node.parentElement) observer.observe(node.parentElement);
    node.addEventListener("load", measure);
    return () => {
      observer.disconnect();
      node.removeEventListener("load", measure);
    };
  }, [displayImage, native.status]);
  useEffect(() => {
    setDrag(null);
    move.current = null;
    resize.current = null;
    setGhosts([]);
    setGuides([]);
  }, [enabled, displayImage, slideNumber, grid, alignmentGuides]);
  const selection = movable.filter((o) => selectedIds.includes(o.object_id));
  const displayGeometry = selection.map(
    (o) =>
      ghosts.find((op) => op.params.object_id === o.object_id)?.params
        .replacement_geometry ?? o.geometry!,
  );
  const rotationTransform = (object: LayoutObject, g: LayoutGeometry) => {
    const degrees = object.rotation?.rotation_degrees ?? 0;
    return degrees
      ? `rotate(${degrees} ${g.x_emu + g.width_emu / 2} ${g.y_emu + g.height_emu / 2})`
      : undefined;
  };
  // Resize handles act on unrotated frames, so rotated selections only move.
  const bounds =
    displayGeometry.length &&
    selection.length === selectedIds.length &&
    selection.every((o) => !o.rotation?.rotation_degrees)
      ? {
          left: Math.min(...displayGeometry.map((g) => g.x_emu)),
          top: Math.min(...displayGeometry.map((g) => g.y_emu)),
          right: Math.max(...displayGeometry.map((g) => g.x_emu + g.width_emu)),
          bottom: Math.max(
            ...displayGeometry.map((g) => g.y_emu + g.height_emu),
          ),
        }
      : null;
  return (
    <>
      {native.controls}
      {enabled && nativeTarget && !nativeTarget.planId ? (
        <div
          className="pw-live-controls"
          role="group"
          aria-label="Live object dragging"
        >
          <div className="button-row">
            <button
              type="button"
              className="secondary-button"
              disabled={
                live.workerBusy || live.phase === "loading" || native.pending
              }
              onClick={() => void live.prepare()}
            >
              {live.workerBusy
                ? "Preparing live dragging…"
                : live.ready
                  ? "Refresh live dragging"
                  : "Prepare live dragging"}
            </button>
            {live.phase !== "off" ? (
              <button
                type="button"
                className="secondary-button"
                onClick={live.stop}
              >
                {live.phase === "running" || live.phase === "loading"
                  ? "Cancel preparation"
                  : "Stop live dragging"}
              </button>
            ) : null}
          </div>
          <p role="status">
            {live.ready
              ? "Live dragging uses PowerPoint pixels. Drag to review a move; changes are saved only after review."
              : live.phase === "running"
                ? "Preparing this saved slide for live dragging in PowerPoint."
                : live.phase === "loading"
                  ? "Loading live dragging pixels."
                  : "Prepare live dragging to see object pixels move with the selection."}
          </p>
          {live.error ? <p role="alert">{live.error}</p> : null}
        </div>
      ) : null}
      <div className={`pw-canvas${enabled ? " pw-canvas-selecting" : ""}`}>
        <img
          ref={img}
          style={live.ready && box && size ? { opacity: 0 } : undefined}
          src={displayImage}
          onError={() => {
            if (native.image) native.rejectImage();
          }}
          alt={`Imported presentation, slide ${slideNumber}`}
        />
        {live.assets && box && size ? (
          <div
            className="pw-native-layers"
            aria-hidden="true"
            style={{
              left: box.left,
              top: box.top,
              width: box.width,
              height: box.height,
              visibility: live.ready ? "visible" : "hidden",
            }}
          >
            <img
              src={live.assets.background}
              alt=""
              onLoad={(event) =>
                live.imageLoaded(
                  0,
                  event.currentTarget.naturalWidth,
                  event.currentTarget.naturalHeight,
                )
              }
              onError={live.imageFailed}
            />
            {live.assets.layers.map((layer, index) => {
              const operation = move.current
                ? ghosts.find((op) => op.params.object_id === layer.objectId)
                : undefined;
              const dx = operation
                ? operation.params.replacement_geometry.x_emu -
                  operation.params.expected_geometry.x_emu
                : 0;
              const dy = operation
                ? operation.params.replacement_geometry.y_emu -
                  operation.params.expected_geometry.y_emu
                : 0;
              return (
                <img
                  key={layer.objectId}
                  data-object-id={layer.objectId}
                  src={layer.value}
                  alt=""
                  style={{
                    transform: `translate(${(dx * box.width) / size.width}px,${(dy * box.height) / size.height}px)`,
                  }}
                  onLoad={(event) =>
                    live.imageLoaded(
                      index + 1,
                      event.currentTarget.naturalWidth,
                      event.currentTarget.naturalHeight,
                    )
                  }
                  onError={live.imageFailed}
                />
              );
            })}
          </div>
        ) : null}
        {enabled && box && size ? (
          <svg
            className="pw-object-overlay"
            aria-label="Select slide objects"
            style={{
              left: box.left,
              top: box.top,
              width: box.width,
              height: box.height,
            }}
            viewBox={`0 0 ${size.width} ${size.height}`}
            preserveAspectRatio="none"
            onPointerDown={(event) => {
              if (event.button !== 0 || event.target !== event.currentTarget)
                return;
              const rect = event.currentTarget.getBoundingClientRect();
              const x = ((event.clientX - rect.left) / rect.width) * size.width;
              const y =
                ((event.clientY - rect.top) / rect.height) * size.height;
              event.currentTarget.setPointerCapture(event.pointerId);
              setDrag({
                x,
                y,
                endX: x,
                endY: y,
                initial:
                  event.shiftKey || event.ctrlKey || event.metaKey
                    ? selectedIds
                    : [],
              });
            }}
            onPointerMove={(event) => {
              if (resize.current) {
                const origin = resize.current;
                const rect = event.currentTarget.getBoundingClientRect();
                if (
                  Math.hypot(
                    event.clientX - origin.clientX,
                    event.clientY - origin.clientY,
                  ) >= 4
                ) {
                  const result = guidedResize(
                    objects,
                    origin.ids,
                    "",
                    origin.handle,
                    ((event.clientX - rect.left) / rect.width) * size.width -
                      origin.x,
                    ((event.clientY - rect.top) / rect.height) * size.height -
                      origin.y,
                    size,
                    grid,
                    event.shiftKey,
                    alignmentGuides && !event.altKey
                      ? {
                          x: (6 * size.width) / rect.width,
                          y: (6 * size.height) / rect.height,
                        }
                      : undefined,
                  );
                  setGhosts(result.operations);
                  setGuides(result.guides);
                }
                return;
              }
              if (move.current) {
                const rect = event.currentTarget.getBoundingClientRect();
                const dx =
                  ((event.clientX - rect.left) / rect.width) * size.width -
                  move.current.x;
                const dy =
                  ((event.clientY - rect.top) / rect.height) * size.height -
                  move.current.y;
                if (
                  Math.hypot(
                    event.clientX - move.current.clientX,
                    event.clientY - move.current.clientY,
                  ) >= 4
                ) {
                  suppressClick.current = true;
                  const result = guidedTranslation(
                    objects,
                    move.current.ids,
                    "",
                    dx,
                    dy,
                    size,
                    grid,
                    alignmentGuides && !event.altKey
                      ? {
                          x: (6 * size.width) / rect.width,
                          y: (6 * size.height) / rect.height,
                        }
                      : undefined,
                  );
                  setGhosts(result.operations);
                  setGuides(result.guides);
                }
                return;
              }
              if (!drag) return;
              const rect = event.currentTarget.getBoundingClientRect();
              setDrag({
                ...drag,
                endX: Math.max(
                  0,
                  Math.min(
                    size.width,
                    ((event.clientX - rect.left) / rect.width) * size.width,
                  ),
                ),
                endY: Math.max(
                  0,
                  Math.min(
                    size.height,
                    ((event.clientY - rect.top) / rect.height) * size.height,
                  ),
                ),
              });
            }}
            onPointerUp={(event) => {
              if (resize.current) {
                const origin = resize.current;
                const rect = event.currentTarget.getBoundingClientRect();
                resize.current = null;
                setGhosts([]);
                setGuides([]);
                if (
                  Math.hypot(
                    event.clientX - origin.clientX,
                    event.clientY - origin.clientY,
                  ) >= 4
                ) {
                  onResize(
                    origin.ids,
                    origin.handle,
                    ((event.clientX - rect.left) / rect.width) * size.width -
                      origin.x,
                    ((event.clientY - rect.top) / rect.height) * size.height -
                      origin.y,
                    event.shiftKey,
                    alignmentGuides && !event.altKey
                      ? {
                          x: (6 * size.width) / rect.width,
                          y: (6 * size.height) / rect.height,
                        }
                      : undefined,
                  );
                }
                if (event.currentTarget.hasPointerCapture(event.pointerId))
                  event.currentTarget.releasePointerCapture(event.pointerId);
                return;
              }
              if (move.current) {
                const origin = move.current;
                const rect = event.currentTarget.getBoundingClientRect();
                const moved =
                  Math.hypot(
                    event.clientX - origin.clientX,
                    event.clientY - origin.clientY,
                  ) >= 4;
                move.current = null;
                resize.current = null;
                setGhosts([]);
                setGuides([]);
                if (moved) {
                  suppressClick.current = true;
                  onMove(
                    origin.ids,
                    ((event.clientX - rect.left) / rect.width) * size.width -
                      origin.x,
                    ((event.clientY - rect.top) / rect.height) * size.height -
                      origin.y,
                    alignmentGuides && !event.altKey
                      ? {
                          x: (6 * size.width) / rect.width,
                          y: (6 * size.height) / rect.height,
                        }
                      : undefined,
                  );
                }
                if (event.currentTarget.hasPointerCapture(event.pointerId))
                  event.currentTarget.releasePointerCapture(event.pointerId);
                return;
              }
              if (!drag) return;
              const rect = event.currentTarget.getBoundingClientRect();
              const endX = Math.max(
                0,
                Math.min(
                  size.width,
                  ((event.clientX - rect.left) / rect.width) * size.width,
                ),
              );
              const endY = Math.max(
                0,
                Math.min(
                  size.height,
                  ((event.clientY - rect.top) / rect.height) * size.height,
                ),
              );
              const bounds = {
                left: Math.min(drag.x, endX),
                right: Math.max(drag.x, endX),
                top: Math.min(drag.y, endY),
                bottom: Math.max(drag.y, endY),
              };
              const ids = movable
                .filter((object) => {
                  const g = object.geometry!;
                  return (
                    g.x_emu < bounds.right &&
                    g.x_emu + g.width_emu > bounds.left &&
                    g.y_emu < bounds.bottom &&
                    g.y_emu + g.height_emu > bounds.top
                  );
                })
                .map((object) => object.object_id);
              onSelect([...new Set([...drag.initial, ...ids])].slice(0, 20));
              setDrag(null);
              if (event.currentTarget.hasPointerCapture(event.pointerId))
                event.currentTarget.releasePointerCapture(event.pointerId);
            }}
            onPointerCancel={() => {
              setDrag(null);
              move.current = null;
              resize.current = null;
              setGhosts([]);
              setGuides([]);
            }}
            onLostPointerCapture={() => {
              setDrag(null);
              move.current = null;
              resize.current = null;
              setGhosts([]);
              setGuides([]);
            }}
            onKeyDown={(event) => {
              if (event.key === "Escape") {
                setEnteredGroup(null);
                setDrag(null);
                move.current = null;
                resize.current = null;
                setGhosts([]);
                setGuides([]);
                onSelect([]);
              }
            }}
          >
            {movable.map((object) => {
              const g = object.geometry!,
                selected = selectedIds.includes(object.object_id);
              const choose = (additive: boolean) =>
                onSelect(
                  additive
                    ? selected
                      ? selectedIds.filter((id) => id !== object.object_id)
                      : [...selectedIds, object.object_id].slice(0, 20)
                    : [object.object_id],
                );
              return (
                <rect
                  key={object.object_id}
                  role="button"
                  tabIndex={0}
                  aria-label={`Select ${object.name} on slide`}
                  aria-pressed={selected}
                  x={g.x_emu}
                  y={g.y_emu}
                  width={g.width_emu}
                  height={g.height_emu}
                  transform={rotationTransform(object, g)}
                  vectorEffect="non-scaling-stroke"
                  className={selected ? "is-selected" : ""}
                  onPointerDown={(event) => {
                    suppressClick.current = false;
                    if (
                      event.button !== 0 ||
                      event.shiftKey ||
                      event.ctrlKey ||
                      event.metaKey
                    )
                      return;
                    event.stopPropagation();
                    const svg = event.currentTarget.ownerSVGElement;
                    if (!svg) return;
                    const rect = svg.getBoundingClientRect();
                    const ids = selected ? selectedIds : [object.object_id];
                    if (!selected) onSelect(ids);
                    suppressClick.current = false;
                    move.current = {
                      x:
                        ((event.clientX - rect.left) / rect.width) * size.width,
                      y:
                        ((event.clientY - rect.top) / rect.height) *
                        size.height,
                      clientX: event.clientX,
                      clientY: event.clientY,
                      ids,
                    };
                    event.currentTarget.setPointerCapture(event.pointerId);
                  }}
                  onClick={(event) => {
                    event.stopPropagation();
                    if (suppressClick.current) {
                      suppressClick.current = false;
                      return;
                    }
                    choose(event.shiftKey || event.ctrlKey || event.metaKey);
                  }}
                  onDoubleClick={(event) => {
                    if (object.kind !== "grpSp") return;
                    event.stopPropagation();
                    setEnteredGroup(object.object_id);
                  }}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      choose(event.shiftKey || event.ctrlKey || event.metaKey);
                    }
                  }}
                />
              );
            })}
            {ghosts.map((operation) => {
              const object = movable.find(
                (item) => item.object_id === operation.params.object_id,
              );
              const g = operation.params.replacement_geometry;
              return (
                <rect
                  key={`ghost:${operation.params.object_id}`}
                  className="pw-object-marquee"
                  pointerEvents="none"
                  x={g.x_emu}
                  y={g.y_emu}
                  width={g.width_emu}
                  height={g.height_emu}
                  transform={object ? rotationTransform(object, g) : undefined}
                  vectorEffect="non-scaling-stroke"
                />
              );
            })}
            {bounds
              ? RESIZE_HANDLES.map(([handle, label]) => {
                  const x = handle.includes("w")
                    ? bounds.left
                    : handle.includes("e")
                      ? bounds.right
                      : (bounds.left + bounds.right) / 2;
                  const y = handle.includes("n")
                    ? bounds.top
                    : handle.includes("s")
                      ? bounds.bottom
                      : (bounds.top + bounds.bottom) / 2;
                  const w = (12 * size.width) / box.width,
                    h = (12 * size.height) / box.height;
                  return (
                    <rect
                      key={`resize:${handle}`}
                      role="button"
                      tabIndex={0}
                      aria-label={`Resize selection ${label}`}
                      className={`pw-resize-handle pw-resize-${handle}`}
                      x={
                        handle.includes("w")
                          ? x - w - w / 6
                          : handle.includes("e")
                            ? x + w / 6
                            : x - w / 2
                      }
                      y={
                        handle.includes("n")
                          ? y - h - h / 6
                          : handle.includes("s")
                            ? y + h / 6
                            : y - h / 2
                      }
                      width={w}
                      height={h}
                      vectorEffect="non-scaling-stroke"
                      onClick={(event) => event.stopPropagation()}
                      onPointerDown={(event) => {
                        if (event.button !== 0) return;
                        event.preventDefault();
                        event.stopPropagation();
                        event.currentTarget.focus();
                        const svg = event.currentTarget.ownerSVGElement;
                        if (!svg) return;
                        const rect = svg.getBoundingClientRect();
                        move.current = null;
                        setDrag(null);
                        setGhosts([]);
                        setGuides([]);
                        resize.current = {
                          x:
                            ((event.clientX - rect.left) / rect.width) *
                            size.width,
                          y:
                            ((event.clientY - rect.top) / rect.height) *
                            size.height,
                          clientX: event.clientX,
                          clientY: event.clientY,
                          ids: [...selectedIds],
                          handle,
                        };
                        svg.setPointerCapture(event.pointerId);
                      }}
                      onKeyDown={(event) => {
                        const delta = grid || 9144;
                        const key = {
                          ArrowLeft: [-delta, 0],
                          ArrowRight: [delta, 0],
                          ArrowUp: [0, -delta],
                          ArrowDown: [0, delta],
                        }[event.key];
                        if (!key || event.ctrlKey || event.metaKey) return;
                        event.preventDefault();
                        event.stopPropagation();
                        onResize(
                          selectedIds,
                          handle,
                          key[0]!,
                          key[1]!,
                          event.shiftKey,
                        );
                      }}
                    />
                  );
                })
              : null}
            {guides.map((guide, index) =>
              guide.gap ? (
                <g
                  key={`${guide.axis}:${index}`}
                  className="pw-spacing-guide"
                  aria-hidden="true"
                  pointerEvents="none"
                >
                  <line
                    className="pw-alignment-guide"
                    vectorEffect="non-scaling-stroke"
                    x1={guide.axis === "x" ? guide.gap.start : guide.gap.cross}
                    x2={guide.axis === "x" ? guide.gap.end : guide.gap.cross}
                    y1={guide.axis === "y" ? guide.gap.start : guide.gap.cross}
                    y2={guide.axis === "y" ? guide.gap.end : guide.gap.cross}
                  />
                  {[guide.gap.start, guide.gap.end].map((edge, tick) => (
                    <line
                      key={tick}
                      className="pw-alignment-guide"
                      vectorEffect="non-scaling-stroke"
                      x1={
                        guide.axis === "x"
                          ? edge
                          : guide.gap!.cross - (3 * size.width) / box.width
                      }
                      x2={
                        guide.axis === "x"
                          ? edge
                          : guide.gap!.cross + (3 * size.width) / box.width
                      }
                      y1={
                        guide.axis === "y"
                          ? edge
                          : guide.gap!.cross - (3 * size.height) / box.height
                      }
                      y2={
                        guide.axis === "y"
                          ? edge
                          : guide.gap!.cross + (3 * size.height) / box.height
                      }
                    />
                  ))}
                </g>
              ) : (
                <line
                  key={`${guide.axis}:${index}`}
                  className="pw-alignment-guide"
                  aria-hidden="true"
                  pointerEvents="none"
                  vectorEffect="non-scaling-stroke"
                  x1={guide.axis === "x" ? guide.position : 0}
                  x2={guide.axis === "x" ? guide.position : size.width}
                  y1={guide.axis === "y" ? guide.position : 0}
                  y2={guide.axis === "y" ? guide.position : size.height}
                />
              ),
            )}
            {drag ? (
              <rect
                className="pw-object-marquee"
                pointerEvents="none"
                x={Math.min(drag.x, drag.endX)}
                y={Math.min(drag.y, drag.endY)}
                width={Math.abs(drag.x - drag.endX)}
                height={Math.abs(drag.y - drag.endY)}
                vectorEffect="non-scaling-stroke"
              />
            ) : null}
          </svg>
        ) : null}
      </div>
    </>
  );
}
