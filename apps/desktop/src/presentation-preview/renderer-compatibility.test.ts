import JSZip from "jszip";
import {
  DOMParser as XmlDomParser,
  XMLSerializer as XmlDomSerializer,
} from "@xmldom/xmldom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { PptxFiles } from "@aiden0z/pptx-renderer";

import { applyPreviewRendererCompatibility } from "./renderer-compatibility";

const PRESENTATION_NS =
  "http://schemas.openxmlformats.org/presentationml/2006/main";
const DRAWING_NS = "http://schemas.openxmlformats.org/drawingml/2006/main";
const PACKAGE_RELATIONSHIP_NS =
  "http://schemas.openxmlformats.org/package/2006/relationships";
const OFFICE_RELATIONSHIP_NS =
  "http://schemas.openxmlformats.org/officeDocument/2006/relationships";
const THEME_OVERRIDE_RELATIONSHIP_TYPE = `${OFFICE_RELATIONSHIP_NS}/themeOverride`;
const DIAGRAM_NS = "http://schemas.openxmlformats.org/drawingml/2006/diagram";
const DIAGRAM_DRAWING_NS =
  "http://schemas.microsoft.com/office/drawing/2008/diagram";
const SLIDE_SIZE = { width: 12_192_000, height: 6_858_000 };

const presentationXml = `<p:presentation xmlns:p="${PRESENTATION_NS}" xmlns:a="${DRAWING_NS}"><p:sldSz cx="${SLIDE_SIZE.width}" cy="${SLIDE_SIZE.height}"/></p:presentation>`;

function shapeXml({
  useBackgroundFill = true,
  width = SLIDE_SIZE.width,
  height = SLIDE_SIZE.height,
  directFill = "solid",
}: {
  useBackgroundFill?: boolean;
  width?: number;
  height?: number;
  directFill?: "solid" | "noFill" | "none";
} = {}): string {
  const useBgFill = useBackgroundFill ? ' useBgFill="1"' : "";
  const fillXml =
    directFill === "solid"
      ? `<a:solidFill><a:schemeClr val="accent1"/></a:solidFill>`
      : directFill === "noFill"
        ? `<a:noFill/>`
        : "";
  return `<p:sp${useBgFill}><p:nvSpPr><p:cNvPr id="2" name="Canvas background"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr><p:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="${width}" cy="${height}"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom>${fillXml}</p:spPr><p:style><a:fillRef idx="1"><a:schemeClr val="accent1"/></a:fillRef></p:style></p:sp>`;
}

function placeholderShapeXml({
  type = "ctrTitle",
  index,
  fillXml = "",
}: {
  type?: string;
  index?: string;
  fillXml?: string;
} = {}): string {
  const indexAttribute = index === undefined ? "" : ` idx="${index}"`;
  return `<p:sp><p:nvSpPr><p:cNvPr id="2" name="Title"/><p:cNvSpPr/><p:nvPr><p:ph type="${type}"${indexAttribute}/></p:nvPr></p:nvSpPr><p:spPr>${fillXml}</p:spPr><p:txBody><a:bodyPr/><a:lstStyle/><a:p><a:r><a:rPr/><a:t>Title</a:t></a:r></a:p></p:txBody></p:sp>`;
}

function slideXml(drawableContent: string): string {
  return `<p:sld xmlns:p="${PRESENTATION_NS}" xmlns:a="${DRAWING_NS}" xmlns:dgm="${DIAGRAM_NS}" xmlns:r="${OFFICE_RELATIONSHIP_NS}"><p:cSld><p:bg><p:bgPr><a:solidFill><a:srgbClr val="FFFFFF"/></a:solidFill></p:bgPr></p:bg><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr/>${drawableContent}</p:spTree></p:cSld></p:sld>`;
}

function pictureGeometryXml(
  geometry = '<a:prstGeom prst="ellipse"><a:avLst/></a:prstGeom>',
): string {
  return `<p:pic><p:nvPicPr><p:cNvPr id="8" name="Oval image" descr="alt text"/><p:cNvPicPr><a:picLocks noChangeAspect="1"/></p:cNvPicPr><p:nvPr/></p:nvPicPr><p:blipFill><a:blip r:embed="rIdImage"/><a:srcRect l="5000"/><a:stretch><a:fillRect/></a:stretch></p:blipFill><p:spPr><a:xfrm><a:off x="100" y="200"/><a:ext cx="1000" cy="800"/></a:xfrm>${geometry}<a:ln w="9525"><a:solidFill><a:srgbClr val="123456"/></a:solidFill></a:ln><a:effectLst><a:outerShdw blurRad="1000"/></a:effectLst></p:spPr></p:pic>`;
}

function pictureGeometryFiles(
  geometry = '<a:prstGeom prst="ellipse"><a:avLst/></a:prstGeom>',
  relationshipTarget = "../media/image.png",
  relationshipTargetMode = "",
): PptxFiles {
  const targetMode = relationshipTargetMode
    ? ` TargetMode="${relationshipTargetMode}"`
    : "";
  const files = makeFiles(
    new Map([
      ["ppt/slides/slide1.xml", slideXml(pictureGeometryXml(geometry))],
    ]),
    new Map(),
    new Map([
      [
        "ppt/slides/_rels/slide1.xml.rels",
        `<Relationships xmlns="${PACKAGE_RELATIONSHIP_NS}"><Relationship Id="rIdImage" Type="${OFFICE_RELATIONSHIP_NS}/image" Target="${relationshipTarget}"${targetMode}/></Relationships>`,
      ],
    ]),
  );
  files.media.set("ppt/media/image.png", new Uint8Array([1, 2, 3]));
  return files;
}

function previewShapeXml(
  shapeName: "pic" | "sp" | "grpSp",
  nonVisualName: "nvPicPr" | "nvSpPr" | "nvGrpSpPr",
  id: string,
  hidden?: string,
  nested = "",
): string {
  const hiddenAttribute = hidden === undefined ? "" : ` hidden="${hidden}"`;
  return `<p:${shapeName}><p:${nonVisualName}><p:cNvPr id="${id}" name="${id}"${hiddenAttribute}/>${shapeName === "grpSp" ? "<p:cNvGrpSpPr/><p:nvPr/>" : shapeName === "sp" ? "<p:cNvSpPr/><p:nvPr/>" : "<p:cNvPicPr/><p:nvPr/>"}</p:${nonVisualName}>${shapeName === "grpSp" ? "<p:grpSpPr/>" : ""}${nested}</p:${shapeName}>`;
}

function smartArtFrame(dataRelationshipId = "rId2"): string {
  return `<p:graphicFrame><p:nvGraphicFramePr><p:cNvPr id="3" name="Diagram"/><p:cNvGraphicFramePr/><p:nvPr/></p:nvGraphicFramePr><p:xfrm><a:off x="0" y="0"/><a:ext cx="100" cy="100"/></p:xfrm><a:graphic><a:graphicData uri="${DIAGRAM_NS}"><dgm:relIds r:dm="${dataRelationshipId}" r:lo="rId3" r:qs="rId4" r:cs="rId5"/></a:graphicData></a:graphic></p:graphicFrame>`;
}

function makeFiles(
  slides: Map<string, string>,
  diagramXml = new Map<string, string>(),
  slideRelationshipXml = new Map<string, string>(),
  slideLayouts = new Map<string, string>(),
): PptxFiles {
  return {
    contentTypes: "",
    presentation: presentationXml,
    presentationRels: "",
    slides,
    slideRels: slideRelationshipXml,
    slideLayouts,
    slideLayoutRels: new Map(),
    slideMasters: new Map(),
    slideMasterRels: new Map(),
    themes: new Map(),
    media: new Map(),
    charts: new Map(),
    chartRels: new Map(),
    chartStyles: new Map(),
    chartColors: new Map(),
    diagramDrawings: diagramXml,
  };
}

function themeOverrideXml(accent2 = "CCCCFF"): string {
  const colors: Record<string, string> = {
    dk1: "000000",
    lt1: "FFFFFF",
    dk2: "111111",
    lt2: "EEEEEE",
    accent1: "FF0000",
    accent2,
    accent3: "00FF00",
    accent4: "0000FF",
    accent5: "FFFF00",
    accent6: "00FFFF",
    hlink: "0000EE",
    folHlink: "551A8B",
  };
  const colorEntries = Object.entries(colors)
    .map(
      ([name, value]) => `<a:${name}><a:srgbClr val="${value}"/></a:${name}>`,
    )
    .join("");
  return `<a:themeOverride xmlns:a="${DRAWING_NS}"><a:clrScheme name="Override">${colorEntries}</a:clrScheme></a:themeOverride>`;
}

function themeOverrideFiles(
  drawableContent: string,
  target = "../theme/themeOverride1.xml",
  targetMode = "",
): PptxFiles {
  const mode = targetMode ? ` TargetMode="${targetMode}"` : "";
  const files = makeFiles(
    new Map([["ppt/slides/slide1.xml", slideXml(drawableContent)]]),
    new Map(),
    new Map([
      [
        "ppt/slides/_rels/slide1.xml.rels",
        `<Relationships xmlns="${PACKAGE_RELATIONSHIP_NS}"><Relationship Id="rIdLayout" Type="${OFFICE_RELATIONSHIP_NS}/slideLayout" Target="../slideLayouts/slideLayout1.xml"/><Relationship Id="rIdThemeOverride" Type="${THEME_OVERRIDE_RELATIONSHIP_TYPE}" Target="${target}"${mode}/></Relationships>`,
      ],
    ]),
    new Map([
      [
        "ppt/slideLayouts/slideLayout1.xml",
        `<p:sldLayout xmlns:p="${PRESENTATION_NS}"/>`,
      ],
    ]),
  );
  files.slideLayoutRels.set(
    "ppt/slideLayouts/_rels/slideLayout1.xml.rels",
    `<Relationships xmlns="${PACKAGE_RELATIONSHIP_NS}"><Relationship Id="rIdMaster" Type="${OFFICE_RELATIONSHIP_NS}/slideMaster" Target="../slideMasters/slideMaster1.xml"/></Relationships>`,
  );
  files.slideMasters.set(
    "ppt/slideMasters/slideMaster1.xml",
    `<p:sldMaster xmlns:p="${PRESENTATION_NS}"><p:clrMap bg1="dk1" tx1="lt1" bg2="dk2" tx2="lt2" accent1="accent1" accent2="accent2" accent3="accent3" accent4="accent4" accent5="accent5" accent6="accent6" hlink="hlink" folHlink="folHlink"/></p:sldMaster>`,
  );
  return files;
}

async function themeOverrideArchive(
  xml = themeOverrideXml(),
): Promise<ArrayBuffer> {
  return new JSZip()
    .file("ppt/theme/themeOverride1.xml", xml)
    .generateAsync({ type: "arraybuffer" });
}

function themeBackgroundImageFiles(
  imageTarget = "../media/texture.png",
  targetMode = "",
): { files: PptxFiles; sourceBytesPromise: Promise<ArrayBuffer> } {
  const mode = targetMode ? ` TargetMode="${targetMode}"` : "";
  const themeRelationshipXml = `<Relationships xmlns="${PACKAGE_RELATIONSHIP_NS}"><Relationship Id="rIdTexture" Type="${OFFICE_RELATIONSHIP_NS}/image" Target="${imageTarget}"${mode}/></Relationships>`;
  const themeXml = `<a:theme xmlns:a="${DRAWING_NS}" xmlns:r="${OFFICE_RELATIONSHIP_NS}"><a:themeElements><a:clrScheme name="Fixture"><a:dk1><a:srgbClr val="000000"/></a:dk1><a:lt1><a:srgbClr val="FFFFFF"/></a:lt1></a:clrScheme><a:fmtScheme name="Fixture"><a:bgFillStyleLst><a:solidFill/><a:solidFill/><a:blipFill rotWithShape="1"><a:blip r:embed="rIdTexture"><a:duotone><a:schemeClr val="phClr"><a:shade val="80000"/><a:lumMod val="80000"/></a:schemeClr><a:schemeClr val="phClr"><a:tint val="98000"/></a:schemeClr></a:duotone></a:blip><a:stretch/></a:blipFill></a:bgFillStyleLst></a:fmtScheme></a:themeElements></a:theme>`;
  const masterPath = "ppt/slideMasters/slideMaster1.xml";
  const masterRelationshipPath = "ppt/slideMasters/_rels/slideMaster1.xml.rels";
  const masterRelationshipXml = `<Relationships xmlns="${PACKAGE_RELATIONSHIP_NS}"><Relationship Id="rIdTheme" Type="${OFFICE_RELATIONSHIP_NS}/theme" Target="../theme/theme1.xml"/></Relationships>`;
  const files = makeFiles(new Map());
  files.slideMasters.set(
    masterPath,
    `<p:sldMaster xmlns:p="${PRESENTATION_NS}" xmlns:a="${DRAWING_NS}" xmlns:r="${OFFICE_RELATIONSHIP_NS}"><p:clrMap bg1="dk1" tx1="lt1" bg2="dk1" tx2="lt1" accent1="dk1" accent2="dk1" accent3="dk1" accent4="dk1" accent5="dk1" accent6="dk1" hlink="dk1" folHlink="dk1"/><p:cSld><p:bg><p:bgRef idx="1003"><a:schemeClr val="bg1"/></p:bgRef></p:bg></p:cSld></p:sldMaster>`,
  );
  files.slideMasterRels.set(masterRelationshipPath, masterRelationshipXml);
  files.themes.set("ppt/theme/theme1.xml", themeXml);
  const image = new Uint8Array(24);
  image.set([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a], 0);
  image.set([0x49, 0x48, 0x44, 0x52], 12);
  new DataView(image.buffer).setUint32(16, 2);
  new DataView(image.buffer).setUint32(20, 1);
  files.mediaResolver = {
    resolve: async (target) =>
      target === "../media/texture.png"
        ? { mediaPath: "ppt/media/texture.png", data: image }
        : undefined,
  };
  const zip = new JSZip();
  zip.file("ppt/theme/_rels/theme1.xml.rels", themeRelationshipXml);
  zip.file("ppt/media/texture.png", image);
  return {
    files,
    sourceBytesPromise: zip.generateAsync({ type: "arraybuffer" }),
  };
}

async function diagramArchive(
  target: string,
  targetMode = "",
): Promise<ArrayBuffer> {
  const zip = new JSZip();
  const mode = targetMode ? ` TargetMode="${targetMode}"` : "";
  zip.file(
    "ppt/diagrams/_rels/drawing1.xml.rels",
    `<Relationships xmlns="${PACKAGE_RELATIONSHIP_NS}"><Relationship Id="rId1" Type="${OFFICE_RELATIONSHIP_NS}/image" Target="${target}"${mode}/></Relationships>`,
  );
  zip.file("ppt/media/icon.png", new Uint8Array([137, 80, 78, 71]));
  return zip.generateAsync({ type: "arraybuffer" });
}

function relationshipXml(target = "../diagrams/drawing1.xml"): string {
  return `<Relationships xmlns="${PACKAGE_RELATIONSHIP_NS}"><Relationship Id="rId1" Type="${OFFICE_RELATIONSHIP_NS}/diagramDrawing" Target="${target}"/><Relationship Id="rId2" Type="${OFFICE_RELATIONSHIP_NS}/diagramData" Target="../diagrams/data1.xml"/></Relationships>`;
}

const cachedDrawingXml = `<dgm:drawing xmlns:dgm="http://schemas.openxmlformats.org/drawingml/2006/diagram" xmlns:p="${PRESENTATION_NS}" xmlns:a="${DRAWING_NS}" xmlns:r="${OFFICE_RELATIONSHIP_NS}"><dgm:spTree><p:pic><p:nvPicPr><p:cNvPr id="2" name="Icon"/><p:cNvPicPr/><p:nvPr/></p:nvPicPr><p:blipFill><a:blip r:embed="rId1"/></p:blipFill><p:spPr/></p:pic></dgm:spTree></dgm:drawing>`;
const cachedImageFillShapeDrawingXml = `<dsp:drawing xmlns:dsp="${DIAGRAM_DRAWING_NS}" xmlns:a="${DRAWING_NS}" xmlns:r="${OFFICE_RELATIONSHIP_NS}"><dsp:spTree><dsp:sp modelId="{fixture}"><dsp:nvSpPr><dsp:cNvPr id="0" name="Icon"/><dsp:cNvSpPr/></dsp:nvSpPr><dsp:spPr><a:xfrm><a:off x="100" y="200"/><a:ext cx="300" cy="400"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom><a:blipFill><a:blip r:embed="rId1"/><a:stretch><a:fillRect/></a:stretch></a:blipFill><a:ln><a:noFill/></a:ln><a:effectLst/></dsp:spPr><dsp:style><a:fillRef idx="1"><a:scrgbClr r="0" g="0" b="0"/></a:fillRef></dsp:style></dsp:sp></dsp:spTree></dsp:drawing>`;

const duotoneBlipXml = `<a:blip r:embed="rIdImage"><a:duotone><a:prstClr val="black"/><a:schemeClr val="accent6"><a:tint val="45000"/><a:satMod val="400000"/></a:schemeClr></a:duotone><a:lum bright="3000" contrast="77000"/></a:blip>`;
const mappedLuminanceDuotoneBlipXml = `<a:blip r:embed="rIdImage"><a:duotone><a:schemeClr val="bg1"><a:shade val="80000"/><a:lumMod val="80000"/></a:schemeClr><a:schemeClr val="bg1"><a:tint val="98000"/></a:schemeClr></a:duotone></a:blip>`;

function clearMaterialPictureProperties(material = "clear"): string {
  return `<p:spPr><a:noFill/><a:scene3d><a:camera prst="orthographicFront"><a:rot lat="0" lon="0" rev="0"/></a:camera><a:lightRig rig="chilly" dir="t"><a:rot lat="0" lon="0" rev="18480000"/></a:lightRig></a:scene3d><a:sp3d prstMaterial="${material}"><a:bevelT h="63500"/></a:sp3d></p:spPr>`;
}

function duotoneMasterFiles(
  secondBlip = duotoneBlipXml,
  firstBlip = duotoneBlipXml,
  pictureProperties: readonly [string, string] = ["", ""],
): PptxFiles {
  const picture = (blip: string, properties: string) =>
    `<p:pic><p:blipFill>${blip}</p:blipFill>${properties}</p:pic>`;
  const files = makeFiles(new Map());
  files.slideMasters.set(
    "ppt/slideMasters/slideMaster1.xml",
    `<p:sldMaster xmlns:p="${PRESENTATION_NS}" xmlns:a="${DRAWING_NS}" xmlns:r="${OFFICE_RELATIONSHIP_NS}"><p:clrMap bg1="dk1" tx1="lt1" bg2="dk2" tx2="lt2" accent1="accent1" accent2="accent2" accent3="accent3" accent4="accent4" accent5="accent5" accent6="accent6" hlink="hlink" folHlink="folHlink"/><p:spTree>${picture(firstBlip, pictureProperties[0])}${picture(secondBlip, pictureProperties[1])}</p:spTree></p:sldMaster>`,
  );
  files.slideMasterRels.set(
    "ppt/slideMasters/_rels/slideMaster1.xml.rels",
    `<Relationships xmlns="${PACKAGE_RELATIONSHIP_NS}"><Relationship Id="rIdImage" Type="${OFFICE_RELATIONSHIP_NS}/image" Target="../media/image.png"/><Relationship Id="rIdTheme" Type="${OFFICE_RELATIONSHIP_NS}/theme" Target="../theme/theme1.xml"/></Relationships>`,
  );
  files.themes.set(
    "ppt/theme/theme1.xml",
    `<a:theme xmlns:a="${DRAWING_NS}"><a:themeElements><a:clrScheme name="Test"><a:dk1><a:srgbClr val="000000"/></a:dk1><a:lt1><a:srgbClr val="FFFFFF"/></a:lt1><a:accent6><a:srgbClr val="FA8D3D"/></a:accent6></a:clrScheme></a:themeElements></a:theme>`,
  );
  const image = new Uint8Array(24);
  image.set([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a], 0);
  image.set([0x49, 0x48, 0x44, 0x52], 12);
  new DataView(image.buffer).setUint32(16, 2);
  new DataView(image.buffer).setUint32(20, 1);
  files.mediaResolver = {
    resolve: async (target) =>
      target === "../media/image.png"
        ? { mediaPath: "ppt/media/image.png", data: image }
        : undefined,
  };
  return files;
}

function stubCanvasDuotonePipeline(outputPixels: number[]): void {
  vi.stubGlobal("createImageBitmap", async () => ({
    width: 2,
    height: 1,
    close: vi.fn(),
  }));
  vi.stubGlobal("document", {
    createElement: () => ({
      width: 0,
      height: 0,
      getContext: () => ({
        drawImage: vi.fn(),
        getImageData: () => ({
          data: new Uint8ClampedArray([0, 0, 0, 255, 255, 255, 0, 255]),
        }),
        putImageData: (imageData: { data: Uint8ClampedArray }) =>
          outputPixels.push(...imageData.data),
      }),
      toBlob: (callback: (blob: Blob | null) => void) =>
        callback(new Blob([new Uint8Array([1, 2, 3])], { type: "image/png" })),
    }),
  });
}

beforeEach(() => {
  vi.stubGlobal("DOMParser", XmlDomParser);
  vi.stubGlobal("XMLSerializer", XmlDomSerializer);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("preview renderer compatibility", () => {
  it("suppresses hidden slide, layout, and master objects only in preview maps", async () => {
    const hiddenSlidePicture = previewShapeXml(
      "pic",
      "nvPicPr",
      "hidden-slide",
      "1",
    );
    const visibleSlidePicture = previewShapeXml(
      "pic",
      "nvPicPr",
      "visible-slide",
      "0",
    );
    const nestedShapes = previewShapeXml(
      "grpSp",
      "nvGrpSpPr",
      "visible-group",
      "off",
      `${previewShapeXml("sp", "nvSpPr", "hidden-nested", "true")}${previewShapeXml("sp", "nvSpPr", "visible-nested")}`,
    );
    const slide = slideXml(
      `${hiddenSlidePicture}${visibleSlidePicture}${nestedShapes}`,
    );
    const layout = slideXml(
      previewShapeXml("pic", "nvPicPr", "hidden-layout", "on"),
    )
      .replace("<p:sld", "<p:sldLayout")
      .replace("</p:sld>", "</p:sldLayout>");
    const master = `<p:sldMaster xmlns:p="${PRESENTATION_NS}" xmlns:a="${DRAWING_NS}"><p:spTree>${previewShapeXml("pic", "nvPicPr", "hidden-master", "true")}${previewShapeXml("pic", "nvPicPr", "visible-master", "false")}</p:spTree></p:sldMaster>`;
    const zip = new JSZip();
    zip.file("ppt/slides/slide1.xml", slide);
    zip.file("ppt/slideLayouts/slideLayout1.xml", layout);
    zip.file("ppt/slideMasters/slideMaster1.xml", master);
    const sourceBytes = await zip.generateAsync({ type: "arraybuffer" });
    const originalBytes = new Uint8Array(sourceBytes).slice();
    const files = makeFiles(
      new Map([["ppt/slides/slide1.xml", slide]]),
      new Map(),
      new Map(),
      new Map([["ppt/slideLayouts/slideLayout1.xml", layout]]),
    );
    files.slideMasters.set("ppt/slideMasters/slideMaster1.xml", master);
    const originalRelationships = `<Relationships xmlns="${PACKAGE_RELATIONSHIP_NS}"/>`;
    files.slideMasterRels.set(
      "ppt/slideMasters/_rels/slideMaster1.xml.rels",
      originalRelationships,
    );

    const report = await applyPreviewRendererCompatibility(sourceBytes, files, {
      repairSmartArtRelationships: false,
    });

    const updatedSlide = files.slides.get("ppt/slides/slide1.xml") ?? "";
    const updatedLayout =
      files.slideLayouts.get("ppt/slideLayouts/slideLayout1.xml") ?? "";
    const updatedMaster =
      files.slideMasters.get("ppt/slideMasters/slideMaster1.xml") ?? "";
    expect(report.hiddenDrawingObjectsSuppressed).toBe(4);
    expect(updatedSlide).not.toContain("hidden-slide");
    expect(updatedSlide).not.toContain("hidden-nested");
    expect(updatedSlide).toContain("visible-slide");
    expect(updatedSlide).toContain("visible-nested");
    expect(updatedLayout).not.toContain("hidden-layout");
    expect(updatedMaster).not.toContain("hidden-master");
    expect(updatedMaster).toContain("visible-master");
    expect(
      files.slideMasterRels.get("ppt/slideMasters/_rels/slideMaster1.xml.rels"),
    ).toBe(originalRelationships);
    expect(new Uint8Array(sourceBytes)).toEqual(originalBytes);
  });

  it("can leave hidden objects intact for isolated compatibility comparisons", async () => {
    const slide = slideXml(
      previewShapeXml("pic", "nvPicPr", "hidden-slide", "1"),
    );
    const sourceBytes = await new JSZip().generateAsync({
      type: "arraybuffer",
    });
    const files = makeFiles(new Map([["ppt/slides/slide1.xml", slide]]));

    const report = await applyPreviewRendererCompatibility(sourceBytes, files, {
      suppressHiddenDrawingObjects: false,
      repairSmartArtRelationships: false,
    });

    expect(report.hiddenDrawingObjectsSuppressed).toBe(0);
    expect(files.slides.get("ppt/slides/slide1.xml")).toBe(slide);
  });

  it("inherits nested group fills into child shapes in preview only", async () => {
    const inheritedImageFill =
      '<a:blipFill><a:blip r:embed="rIdPattern"/><a:stretch><a:fillRect/></a:stretch></a:blipFill>';
    const childShape = "<p:sp><p:spPr><a:grpFill/></p:spPr></p:sp>";
    const nestedGroup = `<p:grpSp><p:grpSpPr><a:grpFill/></p:grpSpPr>${childShape}</p:grpSp>`;
    const unchangedShape =
      '<p:sp><p:spPr><a:solidFill><a:srgbClr val="00FF00"/></a:solidFill></p:spPr></p:sp>';
    const groupedShapes = `<p:grpSp><p:grpSpPr>${inheritedImageFill}</p:grpSpPr>${childShape}${nestedGroup}${unchangedShape}</p:grpSp>`;
    const slide = slideXml(groupedShapes);
    const relationships = `<Relationships xmlns="${PACKAGE_RELATIONSHIP_NS}"><Relationship Id="rIdPattern" Type="${OFFICE_RELATIONSHIP_NS}/image" Target="../media/pattern.jpg"/></Relationships>`;
    const zip = new JSZip();
    zip.file("ppt/slides/slide1.xml", slide);
    zip.file("ppt/slides/_rels/slide1.xml.rels", relationships);
    zip.file("ppt/media/pattern.jpg", new Uint8Array([1, 2, 3]));
    const sourceBytes = await zip.generateAsync({ type: "arraybuffer" });
    const originalBytes = new Uint8Array(sourceBytes).slice();
    const files = makeFiles(
      new Map([["ppt/slides/slide1.xml", slide]]),
      new Map(),
      new Map([["ppt/slides/_rels/slide1.xml.rels", relationships]]),
    );

    const report = await applyPreviewRendererCompatibility(sourceBytes, files, {
      normalizeGroupFills: true,
      repairSmartArtRelationships: false,
    });

    const updatedSlide = files.slides.get("ppt/slides/slide1.xml") ?? "";
    expect(report.groupFillReferencesInherited).toBe(2);
    expect(report.compatibilityPartsSkipped).toBe(0);
    expect(updatedSlide.match(/<p:spPr><a:blipFill>/g)).toHaveLength(2);
    expect(updatedSlide).toContain('<a:solidFill><a:srgbClr val="00FF00"/>');
    expect(updatedSlide).toContain("<p:grpSpPr><a:grpFill/></p:grpSpPr>");
    expect(files.slideRels.get("ppt/slides/_rels/slide1.xml.rels")).toBe(
      relationships,
    );
    expect(new Uint8Array(sourceBytes)).toEqual(originalBytes);
  });

  it("leaves unresolved or ambiguous group fills untouched", async () => {
    const unresolvedSlide = slideXml(
      "<p:grpSp><p:grpSpPr/><p:sp><p:spPr><a:grpFill/></p:spPr></p:sp></p:grpSp>",
    );
    const ambiguousSlide = slideXml(
      '<p:grpSp><p:grpSpPr><a:solidFill><a:srgbClr val="000000"/></a:solidFill><a:noFill/></p:grpSpPr><p:sp><p:spPr><a:grpFill/></p:spPr></p:sp></p:grpSp>',
    );
    const files = makeFiles(
      new Map([
        ["ppt/slides/slide1.xml", unresolvedSlide],
        ["ppt/slides/slide2.xml", ambiguousSlide],
      ]),
    );
    const sourceBytes = await new JSZip().generateAsync({
      type: "arraybuffer",
    });

    const report = await applyPreviewRendererCompatibility(sourceBytes, files, {
      normalizeGroupFills: true,
      repairSmartArtRelationships: false,
    });

    expect(report.groupFillReferencesInherited).toBe(0);
    expect(report.compatibilityPartsSkipped).toBe(1);
    expect(files.slides.get("ppt/slides/slide1.xml")).toBe(unresolvedSlide);
    expect(files.slides.get("ppt/slides/slide2.xml")).toBe(ambiguousSlide);
  });

  it("inherits only a matched layout placeholder's direct solid fill in preview", async () => {
    const inheritedFill =
      '<a:solidFill><a:schemeClr val="bg1"><a:alpha val="72000"/></a:schemeClr></a:solidFill>';
    const layoutPath = "ppt/slideLayouts/slideLayout1.xml";
    const layoutXml = slideXml(placeholderShapeXml({ fillXml: inheritedFill }))
      .replace("<p:sld", "<p:sldLayout")
      .replace("</p:sld>", "</p:sldLayout>");
    const layoutRelationship = `<Relationships xmlns="${PACKAGE_RELATIONSHIP_NS}"><Relationship Id="rIdLayout" Type="${OFFICE_RELATIONSHIP_NS}/slideLayout" Target="../slideLayouts/slideLayout1.xml"/></Relationships>`;
    const files = makeFiles(
      new Map([
        ["ppt/slides/slide1.xml", slideXml(placeholderShapeXml())],
        [
          "ppt/slides/slide2.xml",
          slideXml(placeholderShapeXml({ fillXml: "<a:noFill/>" })),
        ],
        [
          "ppt/slides/slide3.xml",
          slideXml(placeholderShapeXml({ type: "subTitle" })),
        ],
        [
          "ppt/slides/slide4.xml",
          slideXml(placeholderShapeXml()).replace(
            "</p:sld>",
            "<p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sld>",
          ),
        ],
      ]),
      new Map(),
      new Map([
        ["ppt/slides/_rels/slide1.xml.rels", layoutRelationship],
        ["ppt/slides/_rels/slide2.xml.rels", layoutRelationship],
        ["ppt/slides/_rels/slide3.xml.rels", layoutRelationship],
        ["ppt/slides/_rels/slide4.xml.rels", layoutRelationship],
      ]),
      new Map([[layoutPath, layoutXml]]),
    );
    const sourceBytes = await new JSZip().generateAsync({
      type: "arraybuffer",
    });
    const originalBytes = new Uint8Array(sourceBytes).slice();

    const report = await applyPreviewRendererCompatibility(sourceBytes, files, {
      inheritLayoutPlaceholderFills: true,
      repairSmartArtRelationships: false,
    });

    const inheritedSlide = files.slides.get("ppt/slides/slide1.xml") ?? "";
    const explicitNoFillSlide = files.slides.get("ppt/slides/slide2.xml") ?? "";
    const unmatchedSlide = files.slides.get("ppt/slides/slide3.xml") ?? "";
    const mismatchedColorMapSlide =
      files.slides.get("ppt/slides/slide4.xml") ?? "";
    expect(report.layoutPlaceholderFillsInherited).toBe(1);
    expect(inheritedSlide).toContain('<a:solidFill><a:schemeClr val="bg1">');
    expect(inheritedSlide).toContain('<a:alpha val="72000"/>');
    expect(explicitNoFillSlide).not.toContain('val="72000"');
    expect(unmatchedSlide).not.toContain('val="72000"');
    expect(mismatchedColorMapSlide).not.toContain('val="72000"');
    expect(files.slideLayouts.get(layoutPath)).toBe(layoutXml);
    expect(new Uint8Array(sourceBytes)).toEqual(originalBytes);
  });

  it("normalizes supported full-canvas and inset background fills", async () => {
    const acceptedSlide = slideXml(shapeXml({ directFill: "none" }));
    const partialSlide = slideXml(
      shapeXml({ width: SLIDE_SIZE.width / 2, directFill: "none" }),
    );
    const coveredSlide = slideXml(
      `<p:pic/>${shapeXml({ directFill: "none" })}`,
    );
    const inheritedBackgroundSlide = slideXml(
      shapeXml({ directFill: "none" }),
    ).replace(/<p:bg>.*?<\/p:bg>/, "");
    const explicitSolidFillSlide = slideXml(shapeXml());
    const explicitNoFillSlide = slideXml(shapeXml({ directFill: "noFill" }));
    const files = makeFiles(
      new Map([
        ["ppt/slides/slide1.xml", acceptedSlide],
        ["ppt/slides/slide2.xml", partialSlide],
        ["ppt/slides/slide3.xml", coveredSlide],
        ["ppt/slides/slide4.xml", inheritedBackgroundSlide],
        ["ppt/slides/slide5.xml", explicitSolidFillSlide],
        ["ppt/slides/slide6.xml", explicitNoFillSlide],
      ]),
    );
    const sourceBytes = await new JSZip().generateAsync({
      type: "arraybuffer",
    });
    const originalBytes = new Uint8Array(sourceBytes).slice();

    const report = await applyPreviewRendererCompatibility(sourceBytes, files, {
      normalizeBackgroundFills: true,
      repairSmartArtRelationships: false,
    });

    const acceptedOutput = files.slides.get("ppt/slides/slide1.xml") ?? "";
    const partialOutput = files.slides.get("ppt/slides/slide2.xml") ?? "";
    const coveredOutput = files.slides.get("ppt/slides/slide3.xml") ?? "";
    const inheritedBackgroundOutput =
      files.slides.get("ppt/slides/slide4.xml") ?? "";
    const explicitSolidFillOutput =
      files.slides.get("ppt/slides/slide5.xml") ?? "";
    const explicitNoFillOutput =
      files.slides.get("ppt/slides/slide6.xml") ?? "";
    expect(report.backgroundFillShapesNormalized).toBe(4);
    expect(report.backgroundStyleFillReferencesRemoved).toBe(5);
    expect(acceptedOutput).not.toContain('useBgFill="1"');
    expect(acceptedOutput).toContain('<a:srgbClr val="FFFFFF"');
    expect(acceptedOutput).not.toContain("<a:noFill");
    expect(acceptedOutput).not.toContain("<a:fillRef");
    expect(partialOutput).not.toContain('useBgFill="1"');
    expect(partialOutput).toContain("<a:solidFill");
    expect(coveredOutput).not.toContain('useBgFill="1"');
    expect(coveredOutput).toContain("<a:solidFill");
    expect(inheritedBackgroundOutput).toContain('useBgFill="1"');
    expect(inheritedBackgroundOutput).not.toContain("<a:noFill");
    expect(inheritedBackgroundOutput).not.toContain("<a:fillRef");
    expect(explicitSolidFillOutput).toContain('useBgFill="1"');
    expect(explicitSolidFillOutput).toContain("<a:solidFill");
    expect(explicitNoFillOutput).not.toContain('useBgFill="1"');
    expect(explicitNoFillOutput).toContain('<a:srgbClr val="FFFFFF"');
    expect(explicitNoFillOutput).not.toContain("<a:noFill");
    expect(new Uint8Array(sourceBytes)).toEqual(originalBytes);
  });

  it("resolves inset useBgFill shapes only from simple explicit solid backgrounds", async () => {
    const insetShape = shapeXml({
      width: SLIDE_SIZE.width - 500_000,
      height: SLIDE_SIZE.height - 500_000,
      directFill: "none",
    }).replace('<a:off x="0" y="0"/>', '<a:off x="100000" y="100000"/>');
    const noStyleInsetShape = insetShape.replace(
      /<p:style>[\s\S]*?<\/p:style>/,
      "",
    );
    const directFillShape = shapeXml({
      width: SLIDE_SIZE.width - 500_000,
      height: SLIDE_SIZE.height - 500_000,
      directFill: "solid",
    }).replace('<a:off x="0" y="0"/>', '<a:off x="100000" y="100000"/>');
    const ambiguousStyleShape = insetShape.replace(
      "</p:style>",
      '<a:fillRef idx="2"><a:schemeClr val="accent2"/></a:fillRef></p:style>',
    );
    const texturedBackgroundSlide = slideXml(insetShape).replace(
      '<a:solidFill><a:srgbClr val="FFFFFF"/></a:solidFill>',
      '<a:blipFill><a:blip r:embed="rId1"/></a:blipFill>',
    );
    const gradientBackgroundSlide = slideXml(insetShape).replace(
      '<a:solidFill><a:srgbClr val="FFFFFF"/></a:solidFill>',
      '<a:gradFill><a:gsLst><a:gs pos="0"><a:srgbClr val="FFFFFF"/></a:gs></a:gsLst></a:gradFill>',
    );
    const sourceBytes = await new JSZip().generateAsync({
      type: "arraybuffer",
    });
    const originalBytes = new Uint8Array(sourceBytes).slice();
    const files = makeFiles(
      new Map([
        ["ppt/slides/slide1.xml", slideXml(insetShape)],
        ["ppt/slides/slide2.xml", slideXml(noStyleInsetShape)],
        ["ppt/slides/slide3.xml", slideXml(directFillShape)],
        ["ppt/slides/slide4.xml", texturedBackgroundSlide],
        ["ppt/slides/slide5.xml", gradientBackgroundSlide],
        ["ppt/slides/slide6.xml", slideXml(ambiguousStyleShape)],
      ]),
    );

    const report = await applyPreviewRendererCompatibility(sourceBytes, files, {
      normalizeBackgroundFills: true,
      repairSmartArtRelationships: false,
    });

    const normalized = files.slides.get("ppt/slides/slide1.xml") ?? "";
    const normalizedWithoutStyle =
      files.slides.get("ppt/slides/slide2.xml") ?? "";
    expect(report.backgroundFillShapesNormalized).toBe(2);
    expect(report.backgroundStyleFillReferencesRemoved).toBe(1);
    expect(normalized).not.toContain('useBgFill="1"');
    expect(normalized).not.toContain("<a:fillRef");
    expect(normalized).toContain('<a:srgbClr val="FFFFFF"/>');
    expect(normalizedWithoutStyle).not.toContain('useBgFill="1"');
    expect(normalizedWithoutStyle).toContain('<a:srgbClr val="FFFFFF"/>');
    expect(files.slides.get("ppt/slides/slide3.xml")).toContain(
      'useBgFill="1"',
    );
    expect(files.slides.get("ppt/slides/slide4.xml")).toContain(
      'useBgFill="1"',
    );
    expect(files.slides.get("ppt/slides/slide5.xml")).toContain(
      'useBgFill="1"',
    );
    expect(files.slides.get("ppt/slides/slide6.xml")).toContain(
      'useBgFill="1"',
    );
    expect(new Uint8Array(sourceBytes)).toEqual(originalBytes);
  });

  it("removes only the style fill fallback from an explicit transparent canvas", async () => {
    const styleReferences =
      '<a:lnRef idx="1"/><a:effectRef idx="0"/><a:fontRef idx="minor"><a:schemeClr val="tx1"/></a:fontRef>';
    const transparentShape = shapeXml({
      useBackgroundFill: false,
      directFill: "noFill",
    }).replace("</p:style>", `${styleReferences}</p:style>`);
    const targetSlide = slideXml(transparentShape);
    const partialSlide = slideXml(
      shapeXml({
        useBackgroundFill: false,
        width: SLIDE_SIZE.width / 2,
        directFill: "noFill",
      }),
    );
    const coveredSlide = slideXml(`<p:pic/>${transparentShape}`);
    const imageBackgroundSlide = slideXml(
      shapeXml({ directFill: "none" }),
    ).replace(
      /<p:bg>.*?<\/p:bg>/,
      "<p:bg><p:bgPr><a:blipFill><a:blip/></a:blipFill></p:bgPr></p:bg>",
    );
    const directSolidFillSlide = slideXml(shapeXml());
    const zip = new JSZip();
    zip.file("ppt/slides/slide1.xml", targetSlide);
    const sourceBytes = await zip.generateAsync({ type: "arraybuffer" });
    const originalBytes = new Uint8Array(sourceBytes).slice();
    const files = makeFiles(
      new Map([
        ["ppt/slides/slide1.xml", targetSlide],
        ["ppt/slides/slide2.xml", partialSlide],
        ["ppt/slides/slide3.xml", coveredSlide],
        ["ppt/slides/slide4.xml", imageBackgroundSlide],
        ["ppt/slides/slide5.xml", directSolidFillSlide],
      ]),
    );

    const report = await applyPreviewRendererCompatibility(sourceBytes, files, {
      normalizeBackgroundFills: true,
      repairSmartArtRelationships: false,
    });

    const normalized = files.slides.get("ppt/slides/slide1.xml") ?? "";
    expect(report.backgroundStyleFillReferencesRemoved).toBe(2);
    expect(normalized).toContain("<a:noFill");
    expect(normalized).not.toContain("<a:fillRef");
    expect(normalized).toContain('<a:lnRef idx="1"/>');
    expect(normalized).toContain('<a:effectRef idx="0"/>');
    expect(normalized).toContain('<a:fontRef idx="minor">');
    expect(files.slides.get("ppt/slides/slide2.xml")).toContain("<a:fillRef");
    expect(files.slides.get("ppt/slides/slide3.xml")).toContain("<a:fillRef");
    const imageBackgroundOutput =
      files.slides.get("ppt/slides/slide4.xml") ?? "";
    expect(imageBackgroundOutput).toContain('useBgFill="1"');
    expect(imageBackgroundOutput).not.toContain("<a:fillRef");
    expect(files.slides.get("ppt/slides/slide5.xml")).toContain("<a:fillRef");
    expect(new Uint8Array(sourceBytes)).toEqual(originalBytes);
  });

  it("aliases cached SmartArt image relationships without touching the source PPTX", async () => {
    const sourceBytes = await diagramArchive("../media/icon.png");
    const originalBytes = new Uint8Array(sourceBytes).slice();
    const files = makeFiles(
      new Map([["ppt/slides/slide1.xml", slideXml(smartArtFrame())]]),
      new Map([["ppt/diagrams/drawing1.xml", cachedDrawingXml]]),
      new Map([["ppt/slides/_rels/slide1.xml.rels", relationshipXml()]]),
    );

    const report = await applyPreviewRendererCompatibility(sourceBytes, files);

    const drawing =
      files.diagramDrawings.get("ppt/diagrams/drawing1.xml") ?? "";
    const slideRelationships =
      files.slideRels.get("ppt/slides/_rels/slide1.xml.rels") ?? "";
    expect(report.smartArtImageReferencesRepaired).toBe(1);
    expect(report.smartArtRelationshipPartsUpdated).toBe(1);
    expect(drawing).toContain('r:embed="rIdPresenterPreviewImage1"');
    expect(slideRelationships).toContain('Id="rIdPresenterPreviewImage1"');
    expect(slideRelationships).toContain('Target="../media/icon.png"');
    expect(new Uint8Array(sourceBytes)).toEqual(originalBytes);
  });

  it("promotes SmartArt picture-fill shapes to renderable preview pictures", async () => {
    const sourceBytes = await diagramArchive("../media/icon.png");
    const originalBytes = new Uint8Array(sourceBytes).slice();
    const files = makeFiles(
      new Map([["ppt/slides/slide1.xml", slideXml(smartArtFrame())]]),
      new Map([["ppt/diagrams/drawing1.xml", cachedImageFillShapeDrawingXml]]),
      new Map([["ppt/slides/_rels/slide1.xml.rels", relationshipXml()]]),
    );

    const report = await applyPreviewRendererCompatibility(sourceBytes, files);

    const drawing =
      files.diagramDrawings.get("ppt/diagrams/drawing1.xml") ?? "";
    expect(report.smartArtImageReferencesRepaired).toBe(1);
    expect(report.smartArtImageShapesPromoted).toBe(1);
    expect(report.compatibilityPartsSkipped).toBe(0);
    expect(drawing).toContain("<dsp:pic");
    expect(drawing).toContain("<dsp:blipFill");
    expect(drawing).toContain('r:embed="rIdPresenterPreviewImage1"');
    expect(drawing).toContain('<a:off x="100" y="200"/>');
    expect(drawing).toContain("<a:noFill");
    expect(drawing).not.toContain('<dsp:sp modelId="{fixture}"');
    expect(new Uint8Array(sourceBytes)).toEqual(originalBytes);
  });

  it("leaves useBgFill shapes unchanged by default", async () => {
    const sourceBytes = await new JSZip().generateAsync({
      type: "arraybuffer",
    });
    const originalSlide = slideXml(shapeXml());
    const files = makeFiles(
      new Map([["ppt/slides/slide1.xml", originalSlide]]),
    );

    const report = await applyPreviewRendererCompatibility(sourceBytes, files);

    expect(report.backgroundFillShapesNormalized).toBe(0);
    expect(files.slides.get("ppt/slides/slide1.xml")).toBe(originalSlide);
  });

  it("promotes a stretched nonrectangular picture to a shape fill in preview maps", async () => {
    const sourceBytes = await new JSZip().generateAsync({
      type: "arraybuffer",
    });
    const originalBytes = new Uint8Array(sourceBytes).slice();
    const files = pictureGeometryFiles();
    const originalRelationships = files.slideRels.get(
      "ppt/slides/_rels/slide1.xml.rels",
    );
    const originalMedia = files.media.get("ppt/media/image.png")?.slice();

    const report = await applyPreviewRendererCompatibility(sourceBytes, files, {
      normalizePictureFillGeometry: true,
      repairSmartArtRelationships: false,
    });

    const updatedSlide = files.slides.get("ppt/slides/slide1.xml") ?? "";
    expect(report.pictureGeometryImagesPromoted).toBe(1);
    expect(report.pictureGeometryImagesSkipped).toBe(0);
    expect(report.compatibilityPartsSkipped).toBe(0);
    expect(updatedSlide).toContain("<p:sp>");
    expect(updatedSlide).not.toContain("<p:pic>");
    expect(updatedSlide).toContain('<p:cNvPr id="8" name="Oval image"');
    expect(updatedSlide).toContain('descr="alt text"');
    expect(updatedSlide).toContain("<p:cNvSpPr/>");
    expect(updatedSlide).toContain('<a:prstGeom prst="ellipse"');
    expect(updatedSlide).toContain("<a:blipFill>");
    expect(updatedSlide).toContain('r:embed="rIdImage"');
    expect(updatedSlide).toContain('<a:srcRect l="5000"');
    expect(updatedSlide).toContain('<a:ln w="9525"');
    expect(updatedSlide).toContain("<a:outerShdw");
    expect(updatedSlide).toContain("<p:txBody>");
    expect(files.slideRels.get("ppt/slides/_rels/slide1.xml.rels")).toBe(
      originalRelationships,
    );
    expect(files.media.get("ppt/media/image.png")).toEqual(originalMedia);
    expect(new Uint8Array(sourceBytes)).toEqual(originalBytes);
  });

  it.each([
    ["external relationship", "https://example.invalid/image.png", "External"],
    ["missing package media", "../media/missing.png", ""],
  ])(
    "leaves picture geometry unchanged for %s",
    async (_label, target, targetMode) => {
      const sourceBytes = await new JSZip().generateAsync({
        type: "arraybuffer",
      });
      const files = pictureGeometryFiles(undefined, target, targetMode);
      const originalSlide = files.slides.get("ppt/slides/slide1.xml");

      const report = await applyPreviewRendererCompatibility(
        sourceBytes,
        files,
        {
          normalizePictureFillGeometry: true,
          repairSmartArtRelationships: false,
        },
      );

      expect(report.pictureGeometryImagesPromoted).toBe(0);
      expect(report.pictureGeometryImagesSkipped).toBe(1);
      expect(files.slides.get("ppt/slides/slide1.xml")).toBe(originalSlide);
    },
  );

  it("validates and promotes images through the lazy media resolver", async () => {
    const sourceBytes = await new JSZip().generateAsync({
      type: "arraybuffer",
    });
    const files = pictureGeometryFiles();
    files.media.clear();
    const resolve = vi.fn(async (target: string) =>
      target === "../media/image.png"
        ? {
            mediaPath: "ppt/media/image.png",
            data: new Uint8Array([1, 2, 3]),
          }
        : undefined,
    );
    files.mediaResolver = { resolve };

    const report = await applyPreviewRendererCompatibility(sourceBytes, files, {
      normalizePictureFillGeometry: true,
      repairSmartArtRelationships: false,
    });

    expect(report.pictureGeometryImagesPromoted).toBe(1);
    expect(report.pictureGeometryImagesSkipped).toBe(0);
    expect(resolve).toHaveBeenCalledWith("../media/image.png");
    expect(files.slides.get("ppt/slides/slide1.xml")).toContain("<a:blipFill>");
  });

  it("keeps rectangular, custom, and unsupported preset geometry pictures unchanged", async () => {
    const sourceBytes = await new JSZip().generateAsync({
      type: "arraybuffer",
    });
    const rectangularFiles = pictureGeometryFiles(
      '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom>',
    );
    const rectangularSlide = rectangularFiles.slides.get(
      "ppt/slides/slide1.xml",
    );
    const customFiles = pictureGeometryFiles(
      '<a:custGeom><a:avLst/><a:gdLst/><a:ahLst/><a:cxnLst/><a:rect l="l" t="t" r="r" b="b"/><a:pathLst><a:path w="100" h="100"><a:moveTo><a:pt x="0" y="0"/></a:moveTo><a:close/></a:path></a:pathLst></a:custGeom>',
    );
    const customSlide = customFiles.slides.get("ppt/slides/slide1.xml");
    const unsupportedPresetFiles = pictureGeometryFiles(
      '<a:prstGeom prst="round2DiagRect"><a:avLst/></a:prstGeom>',
    );
    const unsupportedPresetSlide = unsupportedPresetFiles.slides.get(
      "ppt/slides/slide1.xml",
    );

    const rectangularReport = await applyPreviewRendererCompatibility(
      sourceBytes,
      rectangularFiles,
      {
        normalizePictureFillGeometry: true,
        repairSmartArtRelationships: false,
      },
    );
    const customReport = await applyPreviewRendererCompatibility(
      sourceBytes,
      customFiles,
      {
        normalizePictureFillGeometry: true,
        repairSmartArtRelationships: false,
      },
    );
    const unsupportedPresetReport = await applyPreviewRendererCompatibility(
      sourceBytes,
      unsupportedPresetFiles,
      {
        normalizePictureFillGeometry: true,
        repairSmartArtRelationships: false,
      },
    );

    expect(rectangularReport.pictureGeometryImagesPromoted).toBe(0);
    expect(rectangularReport.pictureGeometryImagesSkipped).toBe(0);
    expect(rectangularFiles.slides.get("ppt/slides/slide1.xml")).toBe(
      rectangularSlide,
    );
    expect(customReport.pictureGeometryImagesPromoted).toBe(0);
    expect(customReport.pictureGeometryImagesSkipped).toBe(1);
    expect(customFiles.slides.get("ppt/slides/slide1.xml")).toBe(customSlide);
    expect(unsupportedPresetReport.pictureGeometryImagesPromoted).toBe(0);
    expect(unsupportedPresetReport.pictureGeometryImagesSkipped).toBe(1);
    expect(unsupportedPresetFiles.slides.get("ppt/slides/slide1.xml")).toBe(
      unsupportedPresetSlide,
    );
  });

  it("transforms lazy duotone media through a private in-memory relationship", async () => {
    const sourceBytes = await new JSZip().generateAsync({
      type: "arraybuffer",
    });
    const originalBytes = new Uint8Array(sourceBytes).slice();
    const files = duotoneMasterFiles();
    const renderedPixels: number[] = [];
    stubCanvasDuotonePipeline(renderedPixels);

    const report = await applyPreviewRendererCompatibility(sourceBytes, files, {
      normalizeDuotoneImages: true,
      repairSmartArtRelationships: false,
    });

    const master =
      files.slideMasters.get("ppt/slideMasters/slideMaster1.xml") ?? "";
    const relationships =
      files.slideMasterRels.get(
        "ppt/slideMasters/_rels/slideMaster1.xml.rels",
      ) ?? "";
    const [mediaPath, mediaBytes] = [...files.media.entries()][0] ?? [];
    expect(report.duotoneImageReferencesNormalized).toBe(2);
    expect(report.compatibilityPartsSkipped).toBe(0);
    expect(master).not.toContain("<a:duotone");
    expect(master).not.toContain("<a:lum");
    expect(relationships).toContain(
      'Target="../media/_presenter-preview-duotone-',
    );
    expect(mediaPath).toMatch(
      /^ppt\/media\/_presenter-preview-duotone-.*\.png$/,
    );
    expect(mediaBytes).toEqual(new Uint8Array([1, 2, 3]));
    expect(renderedPixels.slice(0, 4)).not.toEqual([0, 0, 0, 255]);
    expect([renderedPixels[3], renderedPixels[7]]).toEqual([255, 255]);
    expect(new Uint8Array(sourceBytes)).toEqual(originalBytes);
  });

  it("approximates the observed clear-material picture opacity in preview only", async () => {
    const sourceBytes = await new JSZip().generateAsync({
      type: "arraybuffer",
    });
    const originalBytes = new Uint8Array(sourceBytes).slice();
    const clearMaterial = clearMaterialPictureProperties();
    const files = duotoneMasterFiles(duotoneBlipXml, duotoneBlipXml, [
      clearMaterial,
      clearMaterial,
    ]);
    const renderedPixels: number[] = [];
    stubCanvasDuotonePipeline(renderedPixels);

    const report = await applyPreviewRendererCompatibility(sourceBytes, files, {
      normalizeDuotoneImages: true,
      repairSmartArtRelationships: false,
    });

    expect(report.duotoneImageReferencesNormalized).toBe(2);
    expect(report.compatibilityPartsSkipped).toBe(0);
    expect([renderedPixels[3], renderedPixels[7]]).toEqual([51, 51]);
    expect(new Uint8Array(sourceBytes)).toEqual(originalBytes);
  });

  it("does not combine clear-material aliases with a different shared image profile", async () => {
    const sourceBytes = await new JSZip().generateAsync({
      type: "arraybuffer",
    });
    const files = duotoneMasterFiles(duotoneBlipXml, duotoneBlipXml, [
      clearMaterialPictureProperties(),
      clearMaterialPictureProperties("plastic"),
    ]);
    const originalMaster =
      files.slideMasters.get("ppt/slideMasters/slideMaster1.xml") ?? "";
    const originalRelationships =
      files.slideMasterRels.get(
        "ppt/slideMasters/_rels/slideMaster1.xml.rels",
      ) ?? "";
    const renderedPixels: number[] = [];
    stubCanvasDuotonePipeline(renderedPixels);

    const report = await applyPreviewRendererCompatibility(sourceBytes, files, {
      normalizeDuotoneImages: true,
      repairSmartArtRelationships: false,
    });

    expect(report.duotoneImageReferencesNormalized).toBe(0);
    expect(report.compatibilityPartsSkipped).toBe(1);
    expect(files.slideMasters.get("ppt/slideMasters/slideMaster1.xml")).toBe(
      originalMaster,
    );
    expect(
      files.slideMasterRels.get("ppt/slideMasters/_rels/slideMaster1.xml.rels"),
    ).toBe(originalRelationships);
    expect(files.media.size).toBe(0);
    expect(renderedPixels).toEqual([]);
  });

  it("resolves master color mappings and luminance modulation for duotone", async () => {
    const sourceBytes = await new JSZip().generateAsync({
      type: "arraybuffer",
    });
    const originalBytes = new Uint8Array(sourceBytes).slice();
    const files = duotoneMasterFiles(
      mappedLuminanceDuotoneBlipXml,
      mappedLuminanceDuotoneBlipXml,
    );
    const renderedPixels: number[] = [];
    stubCanvasDuotonePipeline(renderedPixels);

    const report = await applyPreviewRendererCompatibility(sourceBytes, files, {
      normalizeDuotoneImages: true,
      repairSmartArtRelationships: false,
    });

    expect(report.duotoneImageReferencesNormalized).toBe(2);
    expect(report.compatibilityPartsSkipped).toBe(0);
    expect(renderedPixels).toEqual([0, 0, 0, 255, 5, 5, 5, 255]);
    expect(new Uint8Array(sourceBytes)).toEqual(originalBytes);
  });

  it("leaves a shared image relationship unchanged when its effects differ", async () => {
    const sourceBytes = await new JSZip().generateAsync({
      type: "arraybuffer",
    });
    const files = duotoneMasterFiles('<a:blip r:embed="rIdImage"/>');
    const originalMaster =
      files.slideMasters.get("ppt/slideMasters/slideMaster1.xml") ?? "";
    const originalRelationships =
      files.slideMasterRels.get(
        "ppt/slideMasters/_rels/slideMaster1.xml.rels",
      ) ?? "";

    const report = await applyPreviewRendererCompatibility(sourceBytes, files, {
      normalizeDuotoneImages: true,
      repairSmartArtRelationships: false,
    });

    expect(report.duotoneImageReferencesNormalized).toBe(0);
    expect(files.slideMasters.get("ppt/slideMasters/slideMaster1.xml")).toBe(
      originalMaster,
    );
    expect(
      files.slideMasterRels.get("ppt/slideMasters/_rels/slideMaster1.xml.rels"),
    ).toBe(originalRelationships);
    expect(files.media.size).toBe(0);
  });

  it("normalizes slide theme override colors for preview without changing source bytes", async () => {
    const drawable = `<p:sp><p:spPr><a:solidFill><a:schemeClr val="accent2"/></a:solidFill></p:spPr><p:style><a:fillRef idx="2"><a:schemeClr val="accent2"><a:tint val="50000"/></a:schemeClr></a:fillRef></p:style></p:sp>`;
    const sourceBytes = await themeOverrideArchive();
    const originalBytes = new Uint8Array(sourceBytes).slice();
    const files = themeOverrideFiles(drawable);
    const originalSlide = files.slides.get("ppt/slides/slide1.xml");

    const report = await applyPreviewRendererCompatibility(sourceBytes, files, {
      normalizeThemeOverrideColors: true,
      repairSmartArtRelationships: false,
    });

    const updatedSlide = files.slides.get("ppt/slides/slide1.xml") ?? "";
    expect(report.themeOverrideColorsNormalized).toBe(2);
    expect(report.compatibilityPartsSkipped).toBe(0);
    expect(updatedSlide).toContain('<a:srgbClr val="CCCCFF"/>');
    expect(updatedSlide).toContain('<a:srgbClr val="E6E6FF"/>');
    expect(updatedSlide).not.toContain('<a:schemeClr val="accent2"');
    expect(updatedSlide).not.toBe(originalSlide);
    expect(new Uint8Array(sourceBytes)).toEqual(originalBytes);
  });

  it.each([
    ["external relationship", "../theme/themeOverride1.xml", "External"],
    ["traversal target", "../../../../outside.xml", ""],
    ["absolute target", "/ppt/theme/themeOverride1.xml", ""],
  ])(
    "leaves a slide unchanged for a %s",
    async (_label, target, targetMode) => {
      const drawable = `<p:sp><p:spPr><a:solidFill><a:schemeClr val="accent2"/></a:solidFill></p:spPr></p:sp>`;
      const sourceBytes = await themeOverrideArchive();
      const files = themeOverrideFiles(drawable, target, targetMode);
      const originalSlide = files.slides.get("ppt/slides/slide1.xml");

      const report = await applyPreviewRendererCompatibility(
        sourceBytes,
        files,
        {
          normalizeThemeOverrideColors: true,
          repairSmartArtRelationships: false,
        },
      );

      expect(report.themeOverrideColorsNormalized).toBe(0);
      expect(report.compatibilityPartsSkipped).toBe(1);
      expect(files.slides.get("ppt/slides/slide1.xml")).toBe(originalSlide);
    },
  );

  it("skips an incomplete theme override color scheme", async () => {
    const drawable = `<p:sp><p:spPr><a:solidFill><a:schemeClr val="accent2"/></a:solidFill></p:spPr></p:sp>`;
    const sourceBytes = await themeOverrideArchive(
      `<a:themeOverride xmlns:a="${DRAWING_NS}"><a:clrScheme name="Incomplete"><a:accent2><a:srgbClr val="CCCCFF"/></a:accent2></a:clrScheme></a:themeOverride>`,
    );
    const files = themeOverrideFiles(drawable);
    const originalSlide = files.slides.get("ppt/slides/slide1.xml");

    const report = await applyPreviewRendererCompatibility(sourceBytes, files, {
      normalizeThemeOverrideColors: true,
      repairSmartArtRelationships: false,
    });

    expect(report.themeOverrideColorsNormalized).toBe(0);
    expect(report.compatibilityPartsSkipped).toBe(1);
    expect(files.slides.get("ppt/slides/slide1.xml")).toBe(originalSlide);
  });

  it("repairs only the cached drawing selected by the SmartArt data relationship", async () => {
    const zip = new JSZip();
    for (const drawingNumber of [1, 9]) {
      zip.file(
        `ppt/diagrams/_rels/drawing${drawingNumber}.xml.rels`,
        `<Relationships xmlns="${PACKAGE_RELATIONSHIP_NS}"><Relationship Id="rId1" Type="${OFFICE_RELATIONSHIP_NS}/image" Target="../media/icon.png"/></Relationships>`,
      );
    }
    zip.file("ppt/media/icon.png", new Uint8Array([137, 80, 78, 71]));
    const sourceBytes = await zip.generateAsync({ type: "arraybuffer" });
    const files = makeFiles(
      new Map([["ppt/slides/slide1.xml", slideXml(smartArtFrame("rId2"))]]),
      new Map([
        ["ppt/diagrams/drawing1.xml", cachedDrawingXml],
        ["ppt/diagrams/drawing9.xml", cachedDrawingXml],
      ]),
      new Map([
        [
          "ppt/slides/_rels/slide1.xml.rels",
          `<Relationships xmlns="${PACKAGE_RELATIONSHIP_NS}"><Relationship Id="rId1" Type="${OFFICE_RELATIONSHIP_NS}/diagramDrawing" Target="../diagrams/drawing1.xml"/><Relationship Id="rId2" Type="${OFFICE_RELATIONSHIP_NS}/diagramData" Target="../diagrams/data9.xml"/><Relationship Id="rId3" Type="${OFFICE_RELATIONSHIP_NS}/diagramDrawing" Target="../diagrams/drawing9.xml"/></Relationships>`,
        ],
      ]),
    );

    const report = await applyPreviewRendererCompatibility(sourceBytes, files);

    expect(report.smartArtImageReferencesRepaired).toBe(1);
    expect(files.diagramDrawings.get("ppt/diagrams/drawing1.xml")).toBe(
      cachedDrawingXml,
    );
    expect(files.diagramDrawings.get("ppt/diagrams/drawing9.xml")).toContain(
      'r:embed="rIdPresenterPreviewImage1"',
    );
  });

  it("resolves a bounded theme image background into the preview master map", async () => {
    const fixture = themeBackgroundImageFiles();
    const sourceBytes = await fixture.sourceBytesPromise;
    const originalBytes = new Uint8Array(sourceBytes).slice();
    const transformedPixels: number[] = [];
    stubCanvasDuotonePipeline(transformedPixels);
    const originalMaster = fixture.files.slideMasters.get(
      "ppt/slideMasters/slideMaster1.xml",
    );

    const report = await applyPreviewRendererCompatibility(
      sourceBytes,
      fixture.files,
      {
        normalizeThemeBackgroundImageFills: true,
        normalizeThemeBackgroundImageEffects: true,
        repairSmartArtRelationships: false,
      },
    );

    const updatedMaster = fixture.files.slideMasters.get(
      "ppt/slideMasters/slideMaster1.xml",
    );
    const updatedRelationships = fixture.files.slideMasterRels.get(
      "ppt/slideMasters/_rels/slideMaster1.xml.rels",
    );
    expect(report.themeBackgroundImageFillsResolved).toBe(1);
    expect(report.compatibilityPartsSkipped).toBe(0);
    expect(transformedPixels).toEqual([0, 0, 0, 255, 5, 5, 5, 255]);
    expect(updatedMaster).toContain("<p:bgPr>");
    expect(updatedMaster).not.toContain("<p:bgRef");
    expect(updatedMaster).toContain('r:embed="rIdPresenterPreviewBackground1"');
    expect(updatedMaster).not.toContain("duotone");
    expect(updatedRelationships).toMatch(
      /Type="http:\/\/schemas\.openxmlformats\.org\/officeDocument\/2006\/relationships\/image" Target="\.\.\/media\/_presenter-preview-theme-bg-[^"]+\.png"/,
    );
    expect(
      [...fixture.files.media.keys()].some((path) =>
        path.startsWith("ppt/media/_presenter-preview-theme-bg-"),
      ),
    ).toBe(true);
    expect(updatedMaster).not.toBe(originalMaster);
    expect(new Uint8Array(sourceBytes)).toEqual(originalBytes);
  });

  it("leaves a theme background image unchanged when its image relation is external", async () => {
    const fixture = themeBackgroundImageFiles(
      "https://example.invalid/texture.png",
      "External",
    );
    const sourceBytes = await fixture.sourceBytesPromise;
    const originalMaster = fixture.files.slideMasters.get(
      "ppt/slideMasters/slideMaster1.xml",
    );
    const originalRelationships = fixture.files.slideMasterRels.get(
      "ppt/slideMasters/_rels/slideMaster1.xml.rels",
    );

    const report = await applyPreviewRendererCompatibility(
      sourceBytes,
      fixture.files,
      {
        normalizeThemeBackgroundImageFills: true,
        repairSmartArtRelationships: false,
      },
    );

    expect(report.themeBackgroundImageFillsResolved).toBe(0);
    expect(report.compatibilityPartsSkipped).toBe(1);
    expect(
      fixture.files.slideMasters.get("ppt/slideMasters/slideMaster1.xml"),
    ).toBe(originalMaster);
    expect(
      fixture.files.slideMasterRels.get(
        "ppt/slideMasters/_rels/slideMaster1.xml.rels",
      ),
    ).toBe(originalRelationships);
  });

  it.each([
    ["external targets", "https://example.invalid/image.png", "External"],
    ["traversal targets", "../../../../outside.png", ""],
    ["absolute package targets", "/ppt/media/icon.png", ""],
  ])("does not alias %s", async (_label, target, targetMode) => {
    const sourceBytes = await diagramArchive(target, targetMode);
    const files = makeFiles(
      new Map([["ppt/slides/slide1.xml", slideXml(smartArtFrame())]]),
      new Map([["ppt/diagrams/drawing1.xml", cachedDrawingXml]]),
      new Map([["ppt/slides/_rels/slide1.xml.rels", relationshipXml()]]),
    );

    const report = await applyPreviewRendererCompatibility(sourceBytes, files);

    expect(report.smartArtImageReferencesRepaired).toBe(0);
    expect(files.diagramDrawings.get("ppt/diagrams/drawing1.xml")).toBe(
      cachedDrawingXml,
    );
    expect(files.slideRels.get("ppt/slides/_rels/slide1.xml.rels")).toBe(
      relationshipXml(),
    );
  });
});
