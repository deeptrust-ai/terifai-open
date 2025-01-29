import { createOpenAI } from '@ai-sdk/openai';
import { streamText } from 'ai';

interface CustomPromptGeneratorProps {
  customScenario: string;
  onGeneratedPrompt: (prompt: string) => void;
}

export async function generateCustomPrompt({ 
  customScenario, 
  onGeneratedPrompt,
}: CustomPromptGeneratorProps) {
  try {
    const openai = createOpenAI({
      apiKey: import.meta.env.VITE_OPENAI_API_KEY
    });
    const result = await streamText({
      model: openai('gpt-4-turbo'),
      prompt: "Generate a prompt for an ai agent to impersonate someone in the following scenario: " + customScenario,
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