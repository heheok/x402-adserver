import { useRef, useState } from "react";
import { useMutation } from "@tanstack/react-query";

import { useApi } from "../../lib/api";
import { humanizeError } from "../../lib/errors";
import Icon from "../ui/Icon";
import Progress from "../ui/Progress";
import { Footer, Lbl } from "./Modal";

const TARGET_W = 1920;
const TARGET_H = 1080;
const TARGET_RATIO = TARGET_W / TARGET_H;
// Pre-normalize cap. We re-encode client-side to a 1920×1080 JPEG before
// upload, so the file the server actually receives is small (~150–400 KB).
// 15 MB lets typical phone photos through; anything larger is almost always
// a panorama / RAW dump that we don't want to decode in a browser canvas.
const MAX_INPUT_BYTES = 15 * 1024 * 1024;
const ALLOWED_TYPES = new Set(["image/jpeg", "image/png"]);
const NORMALIZE_QUALITY = 0.92;

type CreativeUploadResponse = {
  creative_id: string;
  creative_url: string;
  width: number;
  height: number;
  format: string;
};

export type CreativeAsset = {
  creative_id: string;
  creative_url: string;
  preview_data_url: string;
  filename: string;
  size_bytes: number;
};

type Props = {
  initial: CreativeAsset | null;
  onComplete: (asset: CreativeAsset) => void;
};

function readImage(
  file: File,
): Promise<{ width: number; height: number; dataUrl: string }> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error("could not read file"));
    reader.onload = () => {
      const dataUrl = reader.result as string;
      const img = new Image();
      img.onerror = () => reject(new Error("not a valid image"));
      img.onload = () =>
        resolve({
          width: img.naturalWidth,
          height: img.naturalHeight,
          dataUrl,
        });
      img.src = dataUrl;
    };
    reader.readAsDataURL(file);
  });
}

function loadImage(src: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error("could not decode image"));
    img.src = src;
  });
}

// Scale-fit any input onto a 1920×1080 black canvas. Letterbox / pillarbox
// preserves the original creative; we pick black because publisher screens
// in our (devnet) inventory are dark-background DOOH boards. Output is JPEG
// because the canvas is opaque after letterboxing — PNG transparency would
// be wasted bytes.
async function normalizeTo1920x1080(
  file: File,
  origDataUrl: string,
  origW: number,
  origH: number,
): Promise<{ file: File; dataUrl: string; resized: boolean }> {
  if (origW === TARGET_W && origH === TARGET_H) {
    return { file, dataUrl: origDataUrl, resized: false };
  }

  const canvas = document.createElement("canvas");
  canvas.width = TARGET_W;
  canvas.height = TARGET_H;
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("Canvas not supported in this browser");
  ctx.fillStyle = "#000000";
  ctx.fillRect(0, 0, TARGET_W, TARGET_H);

  const srcRatio = origW / origH;
  let drawW: number;
  let drawH: number;
  if (srcRatio > TARGET_RATIO) {
    drawW = TARGET_W;
    drawH = Math.round(TARGET_W / srcRatio);
  } else {
    drawH = TARGET_H;
    drawW = Math.round(TARGET_H * srcRatio);
  }
  const dx = Math.round((TARGET_W - drawW) / 2);
  const dy = Math.round((TARGET_H - drawH) / 2);

  ctx.imageSmoothingEnabled = true;
  ctx.imageSmoothingQuality = "high";
  const img = await loadImage(origDataUrl);
  ctx.drawImage(img, dx, dy, drawW, drawH);

  const blob: Blob = await new Promise((resolve, reject) =>
    canvas.toBlob(
      (b) =>
        b ? resolve(b) : reject(new Error("could not encode normalized image")),
      "image/jpeg",
      NORMALIZE_QUALITY,
    ),
  );

  // Keep the user's original filename stem so the GCS object name still
  // reads as "their" creative; just swap to .jpg since we re-encoded.
  const stem = file.name.replace(/\.[^.]+$/, "") || "creative";
  const normalized = new File([blob], `${stem}.jpg`, { type: "image/jpeg" });
  const dataUrl = canvas.toDataURL("image/jpeg", NORMALIZE_QUALITY);
  return { file: normalized, dataUrl, resized: true };
}

export default function StepImage({ initial, onComplete }: Props) {
  const api = useApi();
  const inputRef = useRef<HTMLInputElement>(null);
  const [picked, setPicked] = useState<{
    file: File;
    width: number;
    height: number;
    dataUrl: string;
    resized: boolean;
    originalName: string;
  } | null>(null);
  const [uploaded, setUploaded] = useState<CreativeAsset | null>(initial);
  const [clientError, setClientError] = useState<string | null>(null);
  const [progress, setProgress] = useState<number | null>(null);

  const upload = useMutation<CreativeUploadResponse, Error, File>({
    mutationFn: async (file) => {
      const fd = new FormData();
      fd.append("file", file);
      const res = await api.post<CreativeUploadResponse>(
        "/api/creatives",
        fd,
        {
          headers: { "Content-Type": "multipart/form-data" },
          onUploadProgress: (e) => {
            if (e.total) setProgress(e.loaded / e.total);
            else setProgress(null);
          },
        },
      );
      return res.data;
    },
    onSuccess: (data) => {
      const asset: CreativeAsset = {
        creative_id: data.creative_id,
        creative_url: data.creative_url,
        preview_data_url: picked?.dataUrl ?? "",
        filename: picked?.file.name ?? "creative",
        size_bytes: picked?.file.size ?? 0,
      };
      setUploaded(asset);
    },
  });

  async function handleFile(file: File) {
    setClientError(null);
    setUploaded(null);
    setPicked(null);
    setProgress(null);
    upload.reset();

    if (!ALLOWED_TYPES.has(file.type)) {
      setClientError("Only JPG and PNG are accepted.");
      return;
    }
    if (file.size > MAX_INPUT_BYTES) {
      setClientError(
        `File is ${(file.size / (1024 * 1024)).toFixed(1)} MB — limit is ${(MAX_INPUT_BYTES / (1024 * 1024)).toFixed(0)} MB.`,
      );
      return;
    }

    try {
      const { width, height, dataUrl } = await readImage(file);
      const {
        file: normalizedFile,
        dataUrl: normalizedDataUrl,
        resized,
      } = await normalizeTo1920x1080(file, dataUrl, width, height);
      setPicked({
        file: normalizedFile,
        width: TARGET_W,
        height: TARGET_H,
        dataUrl: normalizedDataUrl,
        resized,
        originalName: file.name,
      });
      upload.mutate(normalizedFile);
    } catch (err) {
      setClientError(err instanceof Error ? err.message : "could not read");
    }
  }

  function handleBrowse() {
    inputRef.current?.click();
  }

  const previewSrc = picked?.dataUrl ?? uploaded?.preview_data_url ?? null;
  // Display the user's original filename, not the .jpg we re-encoded to.
  const filename = picked?.originalName ?? uploaded?.filename ?? null;
  const sizeKb =
    picked?.file.size ?? uploaded?.size_bytes
      ? ((picked?.file.size ?? uploaded?.size_bytes ?? 0) / 1024).toFixed(0)
      : null;
  const validated = uploaded !== null && !upload.isPending;
  const wasResized = picked?.resized ?? false;
  const progressValue =
    upload.isPending && progress !== null
      ? progress
      : upload.isSuccess
        ? 1
        : 0;
  const progressLabel =
    upload.isPending && progress !== null && progress < 1
      ? `Uploading… ${Math.round(progress * 100)}%`
      : upload.isPending
        ? "Validating on server…"
        : null;

  return (
    <>
      <div style={{ padding: 22 }}>
        <Lbl>Upload creative</Lbl>
        <div style={{ marginTop: 6, fontSize: 12, color: "var(--tx-2)" }}>
          JPG or PNG · any size up to 15 MB. We auto-resize to 1920×1080
          (letterboxed if the aspect ratio differs) before serving on partner
          DOOH screens.
        </div>

        <input
          ref={inputRef}
          type="file"
          accept="image/jpeg,image/png"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) handleFile(f);
          }}
          disabled={upload.isPending}
          style={{ display: "none" }}
        />

        {previewSrc ? (
          <div
            className="x-img-preview"
            style={{
              marginTop: 14,
              padding: 14,
              borderRadius: 12,
              border: "1px solid var(--line-1)",
              background: "var(--bg-2)",
              display: "flex",
              gap: 14,
              alignItems: "center",
            }}
          >
            <div
              style={{
                width: 96,
                height: 54,
                borderRadius: 8,
                overflow: "hidden",
                background: "var(--bg-3)",
                flexShrink: 0,
                position: "relative",
              }}
            >
              <img
                src={previewSrc}
                alt="creative preview"
                style={{
                  width: "100%",
                  height: "100%",
                  objectFit: "cover",
                  display: "block",
                }}
              />
              <div
                style={{
                  position: "absolute",
                  bottom: 4,
                  right: 4,
                  fontSize: 9,
                  color: "rgba(255,255,255,0.85)",
                  fontFamily: "var(--font-mono)",
                  background: "rgba(0,0,0,0.45)",
                  padding: "1px 4px",
                  borderRadius: 3,
                }}
              >
                1920×1080
              </div>
            </div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div
                style={{
                  fontSize: 13,
                  fontWeight: 500,
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  whiteSpace: "nowrap",
                }}
              >
                {filename}
              </div>
              <div
                style={{
                  fontSize: 11,
                  color: "var(--tx-2)",
                  marginTop: 2,
                  fontFamily: "var(--font-mono)",
                  display: "flex",
                  gap: 10,
                  alignItems: "center",
                }}
              >
                {sizeKb && <span>{sizeKb} KB</span>}
                {wasResized && (
                  <span
                    style={{
                      color: "var(--x402-blue-hi)",
                      display: "inline-flex",
                      gap: 4,
                      alignItems: "center",
                    }}
                    title="Auto-resized for 1920×1080 DOOH screens"
                  >
                    <Icon name="check" size={11} stroke={2.4} /> resized
                  </span>
                )}
                {validated && (
                  <span
                    style={{
                      color: "var(--sol-teal)",
                      display: "inline-flex",
                      gap: 4,
                      alignItems: "center",
                    }}
                  >
                    <Icon name="check" size={11} stroke={2.4} /> format ok
                  </span>
                )}
              </div>
              <div style={{ marginTop: 8 }}>
                <Progress
                  value={progressValue}
                  color={
                    validated ? "var(--sol-teal)" : "var(--tint-grad-strong)"
                  }
                />
              </div>
            </div>
            <button
              type="button"
              onClick={handleBrowse}
              disabled={upload.isPending}
              style={{
                width: 28,
                height: 28,
                border: 0,
                background: "transparent",
                color: "var(--tx-2)",
                cursor: upload.isPending ? "not-allowed" : "pointer",
                borderRadius: 6,
              }}
              aria-label="Replace"
            >
              <Icon name="close" size={13} />
            </button>
          </div>
        ) : null}

        <button
          type="button"
          onClick={handleBrowse}
          disabled={upload.isPending}
          style={{
            marginTop: 14,
            width: "100%",
            height: previewSrc ? 56 : 96,
            borderRadius: 12,
            border: "1.5px dashed var(--line-2)",
            background: "transparent",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            flexDirection: "column",
            gap: 6,
            color: "var(--tx-2)",
            cursor: upload.isPending ? "wait" : "pointer",
            font: "inherit",
          }}
        >
          <Icon name="upload" size={18} />
          <div style={{ fontSize: 12 }}>
            {previewSrc ? (
              <>
                Drop a different file, or{" "}
                <span
                  style={{ color: "var(--x402-blue-hi)", fontWeight: 500 }}
                >
                  browse
                </span>{" "}
                to swap
              </>
            ) : (
              <>
                Drop a file, or{" "}
                <span
                  style={{ color: "var(--x402-blue-hi)", fontWeight: 500 }}
                >
                  browse
                </span>
              </>
            )}
          </div>
        </button>

        {progressLabel && (
          <div
            style={{
              marginTop: 8,
              fontSize: 11,
              color: "var(--tx-2)",
              fontFamily: "var(--font-mono)",
            }}
          >
            {progressLabel}
          </div>
        )}
        {clientError && (
          <p
            style={{
              marginTop: 10,
              fontSize: 12,
              color: "var(--st-expired)",
              fontFamily: "var(--font-mono)",
            }}
          >
            {clientError}
          </p>
        )}
        {upload.isError && (
          <p
            style={{
              marginTop: 10,
              fontSize: 12,
              color: "var(--st-expired)",
              fontFamily: "var(--font-mono)",
            }}
          >
            {humanizeError(upload.error)}
          </p>
        )}
      </div>
      <Footer
        left={
          validated ? (
            <span
              style={{
                fontSize: 11,
                color: "var(--sol-teal)",
                fontFamily: "var(--font-mono)",
                display: "inline-flex",
                gap: 6,
                alignItems: "center",
              }}
            >
              <Icon name="check" size={11} stroke={2} /> Creative validated
            </span>
          ) : null
        }
        right={
          <button
            className="x-btn x-btn-primary"
            onClick={() => uploaded && onComplete(uploaded)}
            disabled={!uploaded}
          >
            Next <Icon name="arrowRight" size={12} stroke={2} />
          </button>
        }
      />
    </>
  );
}
