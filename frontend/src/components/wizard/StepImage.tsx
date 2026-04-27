import { useRef, useState } from "react";
import { useMutation } from "@tanstack/react-query";

import { useApi } from "../../lib/api";
import { humanizeError } from "../../lib/errors";
import Icon from "../ui/Icon";
import Progress from "../ui/Progress";
import { Footer, Lbl } from "./Modal";

const REQUIRED_W = 1920;
const REQUIRED_H = 1080;
const MAX_BYTES = 5 * 1024 * 1024;
const ALLOWED_TYPES = new Set(["image/jpeg", "image/png"]);

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

export default function StepImage({ initial, onComplete }: Props) {
  const api = useApi();
  const inputRef = useRef<HTMLInputElement>(null);
  const [picked, setPicked] = useState<{
    file: File;
    width: number;
    height: number;
    dataUrl: string;
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
    if (file.size > MAX_BYTES) {
      setClientError(
        `File is ${(file.size / (1024 * 1024)).toFixed(1)} MB — limit is 5 MB.`,
      );
      return;
    }

    try {
      const { width, height, dataUrl } = await readImage(file);
      if (width !== REQUIRED_W || height !== REQUIRED_H) {
        setClientError(
          `Image must be exactly ${REQUIRED_W}×${REQUIRED_H}px (got ${width}×${height}).`,
        );
        return;
      }
      setPicked({ file, width, height, dataUrl });
      upload.mutate(file);
    } catch (err) {
      setClientError(err instanceof Error ? err.message : "could not read");
    }
  }

  function handleBrowse() {
    inputRef.current?.click();
  }

  const previewSrc = picked?.dataUrl ?? uploaded?.preview_data_url ?? null;
  const filename = picked?.file.name ?? uploaded?.filename ?? null;
  const sizeKb =
    picked?.file.size ?? uploaded?.size_bytes
      ? ((picked?.file.size ?? uploaded?.size_bytes ?? 0) / 1024).toFixed(0)
      : null;
  const validated = uploaded !== null && !upload.isPending;
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
          JPG or PNG · 1920×1080 · 5 MB max. Hosted publicly on the ad
          server's GCS bucket and served on partner DOOH screens.
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
