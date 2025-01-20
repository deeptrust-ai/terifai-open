import { useState } from "react";

import { Input } from "@/components/ui/input";

interface VoiceUploadProps {
  onFileSelect: (file: File | null) => void;
}

export const VoiceUpload: React.FC<VoiceUploadProps> = ({ onFileSelect }) => {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);

  const handleFileChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0] || null;
    setSelectedFile(file);
    onFileSelect(file);
    console.log("here is the file:",file);
  };

  return (
    <div className="space-y-2">
      <h3 className="text-sm font-bold">Upload Voice Sample (Optional)</h3>
      <div className="flex gap-2">
        <Input
          type="file"
          accept="audio/*"
          onChange={handleFileChange}
          className="h-10 py-1.5 file:mr-4 file:py-1 file:px-4 file:rounded-md file:border-0 file:text-sm file:font-medium file:bg-primary file:text-primary-foreground hover:file:opacity-80"
        />
      </div>
      {selectedFile && (
        <p className="text-xs text-muted-foreground">
          Selected file: {selectedFile.name}
        </p>
      )}
    </div>
  );
}; 