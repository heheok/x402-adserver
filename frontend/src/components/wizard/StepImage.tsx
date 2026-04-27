import { useRef, useState } from "react";
import { useMutation } from "@tanstack/react-query";

import { useApi } from "../../lib/api";
import { humanizeError } from "../../lib/errors";

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
};

type Props = {
  initial: CreativeAsset | null;
  onComplete: (asset: CreativeAsset) => void;
};

/**
 * Read dimensions from the file via the browser's Image() decoder. Resolves
 * with {w,h,dataUrl} or rejects if the file isn't a decodable image.
 */
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
  const [clientError, setClientError] = useState<string | null>(null);
  // 0..1 client-side, or null when the total isn't reported by the browser.
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
            if (e.total) {
              setProgress(e.loaded / e.total);
            } else {
              setProgress(null);
            }
          },
        },
      );
      return res.data;
    },
    onSuccess: (data) => {
      onComplete({
        creative_id: data.creative_id,
        creative_url: data.creative_url,
        preview_data_url: picked?.dataUrl ?? "",
      });
    },
  });

  async function handleFile(file: File) {
    setClientError(null);
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
      // Auto-upload on valid pick — the user already chose the file, no need
      // for a second confirmation click.
      upload.mutate(file);
    } catch (err) {
      setClientError(err instanceof Error ? err.message : "could not read image");
    }
  }

  const showingExisting = !picked && initial !== null && !upload.isPending;
  const previewSrc = picked?.dataUrl ?? initial?.preview_data_url ?? null;
  const previewLabel = picked
    ? `${picked.file.name} — ${picked.width}×${picked.height}`
    : showingExisting
      ? "Already uploaded"
      : null;

  const progressPct =
    progress !== null ? Math.round(progress * 100) : null;

  return (
    <div>
      <h3>Upload creative</h3>
      <p className="muted footnote">
        JPG or PNG, exactly 1920×1080 px, 5 MB max. The image is hosted publicly
        on the ad server's GCS bucket and served on partner DOOH screens.
      </p>

      <div className="form" style={{ marginTop: "1rem" }}>
        <input
          ref={inputRef}
          type="file"
          accept="image/jpeg,image/png"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) handleFile(f);
          }}
          disabled={upload.isPending}
        />

        {previewSrc && (
          <div
            style={{
              border: "1px solid var(--border)",
              borderRadius: 8,
              padding: "0.5rem",
              marginTop: "0.5rem",
              background: "rgba(255,255,255,0.02)",
            }}
          >
            <img
              src={previewSrc}
              alt="creative preview"
              style={{
                display: "block",
                width: "100%",
                maxWidth: 360,
                height: "auto",
                borderRadius: 4,
              }}
            />
            {previewLabel && (
              <p className="muted footnote" style={{ marginTop: "0.5rem" }}>
                {previewLabel}
              </p>
            )}
          </div>
        )}

        {upload.isPending && (
          <div style={{ marginTop: "0.5rem" }}>
            <div className="bar">
              <div
                className="fill"
                style={{
                  width:
                    progressPct !== null ? `${progressPct}%` : "100%",
                  // Indeterminate fallback when total isn't known.
                  opacity: progressPct === null ? 0.4 : 1,
                }}
              />
            </div>
            <p className="muted footnote" style={{ marginTop: "0.35rem" }}>
              {progressPct !== null && progressPct < 100
                ? `Uploading… ${progressPct}%`
                : "Validating on server…"}
            </p>
          </div>
        )}

        {clientError && <p className="error">{clientError}</p>}
        {upload.isError && (
          <p className="error">{humanizeError(upload.error)}</p>
        )}
      </div>

      {showingExisting && (
        <div className="actions" style={{ marginTop: "1rem" }}>
          <button
            type="button"
            onClick={() => initial && onComplete(initial)}
          >
            Continue with existing
          </button>
          <span className="muted footnote">
            Or pick a new file above to replace.
          </span>
        </div>
      )}
    </div>
  );
}
