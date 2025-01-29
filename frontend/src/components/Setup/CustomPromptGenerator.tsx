import { useState } from "react";
import { createOpenAI } from '@ai-sdk/openai';
import { streamText } from 'ai';
import { Loader } from "lucide-react";

import { Button } from "../ui/button";

interface CustomPromptGeneratorProps {
  customPrompt: string;
  onGeneratedPrompt: (prompt: string) => void;
  isVisible: boolean;
}

export function CustomPromptGenerator({ 
  customPrompt, 
  onGeneratedPrompt,
  isVisible 
}: CustomPromptGeneratorProps) {
  const [isGenerating, setIsGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function processCustomPrompt(prompt: string) {
    try {
      const openai = createOpenAI({
        apiKey: import.meta.env.VITE_OPENAI_API_KEY
      });
      const result = await streamText({
        model: openai('gpt-4-turbo'),
        prompt: "Generate a prompt for an ai agent to impersonate someone in the following scenario: " + prompt,
      });

      let fullResponse = '';
      for await (const textPart of result.textStream) {
        fullResponse += textPart;
        onGeneratedPrompt(fullResponse);
      }
      
      return fullResponse;
    } catch (error) {
      console.error('Error processing prompt:', error);
      throw error;
    } 
  }

  async function handleGeneratePrompt() {
    if (!customPrompt) return;
    
    setIsGenerating(true);
    setError(null);
    try {
      await processCustomPrompt(customPrompt);
    } catch (error) {
      setError("Failed to generate prompt");
    } finally {
      setIsGenerating(false);
    }
  }

  if (!isVisible) return null;

  return (
    <div className="space-y-4">
      <Button 
        onClick={handleGeneratePrompt}
        disabled={!customPrompt || isGenerating}
        className="w-full"
      >
        {isGenerating ? (
          <>
            <Loader className="mr-2 h-4 w-4 animate-spin" />
            Generating...
          </>
        ) : (
          'Generate Prompt'
        )}
      </Button>
      {error && (
        <p className="text-sm text-red-500">{error}</p>
      )}
    </div>
  );
} 