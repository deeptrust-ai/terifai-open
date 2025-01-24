import { useState } from "react";

import { Input } from "@/components/ui/input";

interface VoiceUploadProps {
  onFileSelect: (file: File | null) => void;
  serverUrl: string;
}

export const VoiceUpload: React.FC<VoiceUploadProps> = ({ onFileSelect }) => {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);

  const checkAudioDuration = (file: File): Promise<number> => {
    return new Promise((resolve) => {
      const audio = new Audio();
      audio.src = URL.createObjectURL(file);
      audio.addEventListener('loadedmetadata', () => {
        URL.revokeObjectURL(audio.src);
        resolve(audio.duration);
      });
    });
  };

  const handleFileChange = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0] || null;
    setError(null);
    
    if (file) {
      const duration = await checkAudioDuration(file);
      if (duration < 10) {
        setError("Audio file must be at least 10 seconds long");
        setSelectedFile(null);
        onFileSelect(null);
        return;
      } else if (duration > 20) {
        setError("Audio file must be less than 20 seconds long");
        setSelectedFile(null);
        onFileSelect(null);
        return;
      }
      setSelectedFile(file);
      onFileSelect(file);
    } else {
      setSelectedFile(null);
      onFileSelect(null);
    }
  };

  return (
    <div className="space-y-2">
      <h3 className="text-sm font-bold">Upload Voice Sample (Optional)</h3>
      <div className="flex gap-2">
        <Input
          type="file"
          accept="audio/wav,audio/mp3"
          onChange={handleFileChange}
          className="h-10 py-1.5 file:mr-4 file:py-1 file:px-4 file:rounded-md file:border-0 file:text-sm file:font-medium file:bg-primary file:text-primary-foreground hover:file:opacity-80"
        />
      </div>
      {error && (
        <p className="text-xs text-red-500">{error}</p>
      )}
      {selectedFile && !error && (
        <p className="text-xs text-muted-foreground">
          Selected file: {selectedFile.name}
        </p>
      )}
    </div>
  );
}; 