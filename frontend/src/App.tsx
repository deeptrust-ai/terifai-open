import { useState } from "react";
import { useDaily } from "@daily-co/daily-react";
import { Ear, Loader } from "lucide-react";

import MaintenancePage from "./components/MaintenancePage";
import Session from "./components/Session";
import { Configure, PromptSelect } from "./components/Setup";
import { Alert } from "./components/ui/alert";
import { Button } from "./components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "./components/ui/card";
import { fetch_create_room, fetch_start_agent } from "./actions";

const isMaintenanceMode = import.meta.env.VITE_MAINTENANCE_MODE === "true";

type State =
  | "configuring_step1"
  | "configuring_step2"
  | "requesting_agent"
  | "connecting"
  | "connected"
  | "started"
  | "finished"
  | "error";


// Server URL (ensure trailing slash)
let serverUrl = import.meta.env.VITE_SERVER_URL;
if (serverUrl && !serverUrl.endsWith("/")) serverUrl += "/";

// Auto room creation (requires server URL)
const autoRoomCreation = parseInt(import.meta.env.VITE_MANUAL_ROOM_ENTRY)
  ? false
  : true;

// Query string for room URL
const roomQs = new URLSearchParams(window.location.search).get("room_url");

// Mic mode
const isOpenMic = parseInt(import.meta.env.VITE_OPEN_MIC) ? true : false;

export default function App() {
  const daily = useDaily();

  const [state, setState] = useState<State>("configuring_step1");
  const [selectedPrompt, setSelectedPrompt] = useState("default");
  const [error, setError] = useState<string | null>(null);
  const [startAudioOff, setStartAudioOff] = useState<boolean>(false);
  const [roomUrl] = useState<string | null>(roomQs || null);

  async function start(selectedPrompt: string, redirect: boolean) {
    if (!daily || (!roomUrl && !autoRoomCreation)) return;

    let data;

    // Request agent to start, or join room directly
    if (import.meta.env.VITE_SERVER_URL) {
      // Request a new agent to join the room
      setState("requesting_agent");

      try {
        // Fetch the default daily configuration
        const config = await fetch_create_room(serverUrl);

        if (config.error) {
          setError(config.detail);
          setState("error");
          return;
        }

        // Start the agent with the room URL and token
        data = await fetch_start_agent(
          config.room_url,
          config.token,
          serverUrl,
          selectedPrompt
        );

        if (data.error) {
          setError(data.detail);
          setState("error");
          return;
        }

        // Either redirect or show Session based on redirect parameter
        if (redirect) {
          window.location.href = config.room_url;
        } else {
          setState("connected");
        }
      } catch (e) {
        setError(`Unable to connect to the bot server at '${serverUrl}'`);
        setState("error");
        return;

      }
    }

    // Join the daily session, passing through the url and token
    setState("connecting");

    try {
      await daily.join({
        url: data?.room_url || roomUrl,
        token: data?.token || "",
        videoSource: false,
        startAudioOff: startAudioOff,
      });
    } catch (e) {
      setError(`Unable to join room: '${data?.room_url || roomUrl}'`);
      setState("error");
      return;
    }
    // Either redirect or show Session based on redirect parameter
    if (redirect) {
      window.location.href = data?.room_url || roomUrl;
    } else {
      setState("connected");
    }
  }

  async function leave() {
    await daily?.leave();
    await daily?.destroy();
    setState("configuring_step1");
  }

  if (isMaintenanceMode) {
    return <MaintenancePage />;
  }

  if (state === "error") {
    return (
      <Alert intent="danger" title="An error occurred">
        {error}
      </Alert>
    );
  }

  if (state === "connected") {
    return (
      <Session
        onLeave={() => leave()}
        openMic={isOpenMic}
        startAudioOff={startAudioOff}
      />
    );
  }

  if (state === "configuring_step1") {
    return (
      <Card shadow className="animate-appear max-w-lg">
        <CardHeader>
          <CardTitle>Configure your devices</CardTitle>
          <CardDescription>
            Please configure your microphone and speakers below
          </CardDescription>
        </CardHeader>
        <CardContent stack>
          <div className="flex flex-row gap-2 bg-primary-50 px-4 py-2 md:p-2 text-sm items-center justify-center rounded-md font-medium text-pretty">
            <Ear className="size-7 md:size-5 text-primary-400" />
            Works best in a quiet environment with a good internet.
          </div>
          <Configure
            startAudioOff={startAudioOff}
            handleStartAudioOff={() => setStartAudioOff(!startAudioOff)}
          />
        </CardContent>
        <CardFooter>
          <Button
            fullWidthMobile
            onClick={() => setState("configuring_step2")}
          >
            Next
          </Button>
        </CardFooter>
      </Card>
    );
  }

  if (state === "configuring_step2") {
    return (
      <Card shadow className="animate-appear max-w-lg">
        <CardHeader className="relative space-y-6">
          <Button
            variant="ghost"
            size="sm"
            className="absolute left-4 top-4 text-muted-foreground hover:text-foreground hover:bg-gray-50"
            onClick={() => setState("configuring_step1")}
          >
            ← Back
          </Button>
          <div className="space-y-1.5 pt-6">
            <CardTitle>Customize Bot Behavior</CardTitle>
            <CardDescription>
              Choose how you want the bot to interact
            </CardDescription>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <PromptSelect
              selectedSetting={selectedPrompt}
              onSettingChange={setSelectedPrompt}
            />
          </div>
        </CardContent>
        <CardFooter className="flex flex-col gap-2">
          <div className="flex gap-3 w-full">
            <div className="flex-1">
              <div className="text-xs text-primary font-bold text-center mb-1.5 invisible">
                (Coming Soon 🤫)
              </div>
              <Button
                fullWidthMobile
                size="lg"
                className="w-full"
                onClick={() => start(selectedPrompt, false)}
              >
                Let's Chat 😊
              </Button>
              <p className="text-xs text-muted-foreground mt-1.5 text-center">
                1:1 conversation with TerifAI
              </p>
            </div>
            <div className="flex-1">
              <div className="text-xs text-primary font-bold text-center mb-1.5">
                (Coming Soon 🤫)
              </div>
              <Button
                fullWidthMobile
                size="lg"
                className="w-full"
                onClick={() => start(selectedPrompt, true)}
                disabled={true}
              >
                Join Call ☎️
              </Button>
              <p className="text-xs text-muted-foreground mt-1.5 text-center">
                Open video call with TerifAI
              </p>
            </div>
          </div>
        </CardFooter>
      </Card>
    );
  }

  return (
    <Card shadow className="animate-appear max-w-lg">
      <CardContent className="flex flex-col items-center justify-center py-12 gap-4">
        <div className="mt-8">
          <Loader className="h-8 w-8 animate-spin text-primary" />
        </div>
        <CardTitle className="text-lg font-medium">
          {state === "requesting_agent" ? "Starting AI Assistant..." : "Connecting to call..."}
        </CardTitle>
        <CardDescription className="text-center text-sm text-muted-foreground">
          Depending on traffic, this may take 1 to 2 minutes...
        </CardDescription>
      </CardContent>
    </Card>
  );
}
