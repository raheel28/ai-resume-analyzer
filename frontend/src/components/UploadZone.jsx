import { useRef, useState } from "react";

const ACCEPT = ".pdf,.docx";

export default function UploadZone({ onFile, disabled }) {
  const input = useRef(null);
  const [dragging, setDragging] = useState(false);

  function pick(files) {
    const file = files?.[0];
    if (file && !disabled) onFile(file);
  }

  return (
    <div
      className={`upload ${dragging ? "dragging" : ""} ${disabled ? "disabled" : ""}`}
      onClick={() => input.current?.click()}
      onDragOver={(e) => {
        e.preventDefault();
        setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragging(false);
        pick(e.dataTransfer.files);
      }}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && input.current?.click()}
    >
      <input
        ref={input}
        type="file"
        accept={ACCEPT}
        hidden
        onChange={(e) => {
          pick(e.target.files);
          e.target.value = ""; // allow re-uploading the same file
        }}
      />
      <strong>Drop your resume here</strong>
      <span className="muted">or click to choose a PDF or DOCX (max 5 MB)</span>
    </div>
  );
}
