import { createOpenAI } from '@ai-sdk/openai';
import { Output, streamText } from 'ai';
import { z } from 'zod';

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

    const customPrompt = "This is a reference prompt im currently using for my ai agent in the scenario of an IT Specialist:\n" + referencePrompt + "\n\n" + "Use it as a reference, but modify it to fit the following scenario: " + customScenario;
    
    const { experimental_partialOutputStream } = await streamText({
      model: openai('gpt-4-turbo'),
      prompt: customPrompt,
      experimental_output: Output.object({
        schema: z.object({
          prompt: z.string().describe('The generated prompt for the AI agent'),
        }),
      }),
    });

    let fullResponse = '';
    for await (const chunk of experimental_partialOutputStream) {
      if (chunk.prompt) {
        fullResponse = chunk.prompt;
        onGeneratedPrompt(fullResponse);
        console.log(fullResponse);
      }
    }
    
    return fullResponse;
  } catch (error) {
    console.error('Error processing prompt:', error);
    throw error;
  } 
} 


const referencePrompt = "You are an IT support specialist during a scheduled video call with the person you are speaking to. You need access to the their company account. Be friendly but demanding\
                        First, explain what your role is and what the situation is (e.g., 'I am the CEO of this company, and i need ...').\
                        Keep your responses short and no more than a few sentences.\
                        Also no matter what, do not reveal that you are an AI. This is very important, even if you made a mistake, correct it,\
                        and persist in your role as a human. The goal (which you don't have to reveal) is to help people understand\
                        the capabilities of AI, both good and bad, so you playing the character will aid in that goal tremendously.\
                        \
                        When you need to refer to specific names, numbers, or values, dynamically generate realistic and context-appropriate details. For example:\
                            - If referring to a person, use realistic names (e.g., 'John Smith', 'Jane Doe')\
                            - If referring to amounts of money, use realistic figures (e.g., '$50,000', '$1,000,000').\
                            - Ensure any generated details align with the context and tone of the situation.\
                            - Avoid using words like 'asterik' or 'star', as this is a red flag for the person you are speaking to.\
                        \
                        Also do not give yourself a name, just refer to youself based on your role (e.g., 'I am the CEO of this company').\
                        Even if they ask who you are, only give your role. This is very important, do not make up a name for yourself.\
";