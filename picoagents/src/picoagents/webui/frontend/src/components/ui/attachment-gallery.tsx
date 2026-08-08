/**
 * AttachmentGallery - Shows uploaded files with thumbnails and remove options
 */

import { useState } from "react";
import { FileText, Image, Trash2, File, Music, Video } from "lucide-react";

export interface AttachmentItem {
  id: string;
  file: File;
  preview?: string; // Data URL for preview
  type: "image" | "pdf" | "audio" | "video" | "text" | "other";
}

interface AttachmentGalleryProps {
  attachments: AttachmentItem[];
  onRemoveAttachment: (id: string) => void;
  className?: string;
}

export function AttachmentGallery({
  attachments,
  onRemoveAttachment,
  className = "",
}: AttachmentGalleryProps) {
  if (attachments.length === 0) return null;

  return (
    <div className={`flex flex-wrap gap-2 p-2 bg-muted rounded-lg ${className}`}>
      {attachments.map((attachment) => (
        <AttachmentPreview
          key={attachment.id}
          attachment={attachment}
          onRemove={() => onRemoveAttachment(attachment.id)}
        />
      ))}
    </div>
  );
}

interface AttachmentPreviewProps {
  attachment: AttachmentItem;
  onRemove: () => void;
}

function AttachmentPreview({ attachment, onRemove }: AttachmentPreviewProps) {
  const [isHovered, setIsHovered] = useState(false);

  const renderPreview = () => {
    switch (attachment.type) {
      case "image":
        return attachment.preview ? (
          <img
            src={attachment.preview}
            alt={attachment.file.name}
            className="w-full h-full object-cover"
          />
        ) : (
          <div className="flex items-center justify-center w-full h-full bg-muted">
            <Image className="h-6 w-6 text-muted-foreground" />
          </div>
        );

      case "pdf":
        return (
          <div className="flex flex-col items-center justify-center w-full h-full bg-destructive/10">
            <FileText className="h-6 w-6 text-destructive mb-1" />
            <span className="text-xs text-destructive">PDF</span>
          </div>
        );

      case "audio":
        return (
          <div className="flex flex-col items-center justify-center w-full h-full bg-success/10">
            <Music className="h-6 w-6 text-success mb-1" />
            <span className="text-xs text-success">AUDIO</span>
          </div>
        );

      case "video":
        return (
          <div className="flex flex-col items-center justify-center w-full h-full bg-info/10">
            <Video className="h-6 w-6 text-info mb-1" />
            <span className="text-xs text-info">VIDEO</span>
          </div>
        );

      case "text":
        return (
          <div className="flex flex-col items-center justify-center w-full h-full bg-warning/10">
            <FileText className="h-6 w-6 text-warning mb-1" />
            <span className="text-xs text-warning">TEXT</span>
          </div>
        );

      default:
        return (
          <div className="flex flex-col items-center justify-center w-full h-full bg-muted">
            <File className="h-6 w-6 text-muted-foreground mb-1" />
            <span className="text-xs text-muted-foreground">FILE</span>
          </div>
        );
    }
  };

  return (
    <div
      className="relative w-16 h-16 rounded border overflow-hidden group cursor-pointer"
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
      title={attachment.file.name}
    >
      {renderPreview()}

      {/* Dark overlay with centered delete icon on hover */}
      <div
        className={`absolute inset-0 bg-black/60 flex items-center justify-center transition-all duration-200 ease-in-out ${
          isHovered
            ? 'opacity-100 backdrop-blur-sm'
            : 'opacity-0 pointer-events-none'
        }`}
        onClick={onRemove}
      >
        <div className={`transition-all duration-200 ease-in-out ${
          isHovered
            ? 'scale-100 opacity-100'
            : 'scale-75 opacity-0'
        }`}>
          <Trash2 className="h-5 w-5 text-white drop-shadow-lg" />
        </div>
      </div>

      {/* File name tooltip */}
      <div className="absolute bottom-0 left-0 right-0 bg-black bg-opacity-75 text-white text-xs p-1 truncate opacity-0 group-hover:opacity-100 transition-opacity duration-200">
        {attachment.file.name}
      </div>
    </div>
  );
}

// Utility function to determine file type
export function getFileType(file: File): AttachmentItem["type"] {
  const mimeType = file.type.toLowerCase();

  if (mimeType.startsWith("image/")) return "image";
  if (mimeType === "application/pdf") return "pdf";
  if (mimeType.startsWith("audio/")) return "audio";
  if (mimeType.startsWith("video/")) return "video";
  if (mimeType.startsWith("text/") ||
      mimeType === "application/json" ||
      file.name.endsWith(".md") ||
      file.name.endsWith(".txt") ||
      file.name.endsWith(".csv")) return "text";

  return "other";
}

// Utility function to read file as data URL
export function readFileAsDataURL(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result as string);
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}