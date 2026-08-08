/**
 * Utility functions for working with PicoAgents messages
 * Including conversion between frontend file uploads and MultiModalMessage format
 */

import type {
  MultiModalMessage,
} from '@/types';

/**
 * Convert a File object to base64 data URI
 */
async function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = reader.result as string;
      // Extract just the base64 part (remove data:mime;base64, prefix)
      const base64 = result.split(',')[1];
      resolve(base64);
    };
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

/**
 * Create a MultiModalMessage from a file upload and text
 */
export async function createMultiModalMessage(
  text: string,
  file: File,
  source: string = "user"
): Promise<MultiModalMessage> {
  const base64Data = await fileToBase64(file);

  const message: MultiModalMessage = {
    role: "user",
    content: text || `Uploaded ${file.type} file: ${file.name}`,
    source: source,
    mime_type: file.type || "application/octet-stream",
    data: base64Data,
    metadata: {
      filename: file.name,
      size: file.size,
      lastModified: file.lastModified
    }
  };

  return message;
}






/**
 * Example usage in a component:
 *
 * const handleFileUpload = async (file: File, textMessage: string) => {
 *   try {
 *     const multiModalMsg = await createMultiModalMessage(textMessage, file, "user");
 *
 *     // Send to backend
 *     const response = await apiClient.runEntity(agentId, {
 *       messages: [...previousMessages, multiModalMsg]
 *     });
 *   } catch (error) {
 *     console.error('Failed to send multimodal message:', error);
 *   }
 * };
 */