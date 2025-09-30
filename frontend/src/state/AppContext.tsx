import { createContext, useContext, useReducer, type ReactNode } from "react";
import type { Dispatch, ReactElement } from "react";
import type {
  AppAction,
  AppState,
  ChatMessage,
  DocumentRecord,
  SchemaSummary,
  BackendSchema,
} from "./types";

const initialState: AppState = {
  connection: {
    status: "disconnected",
  },
  documents: [],
  chat: [],
  ui: {
    isDatabaseModalOpen: false,
    isDocumentModalOpen: false,
  },
};

function appReducer(state: AppState, action: AppAction): AppState {
  switch (action.type) {
    case "OPEN_DATABASE_MODAL":
      return { ...state, ui: { ...state.ui, isDatabaseModalOpen: true } };
    case "CLOSE_DATABASE_MODAL":
      return { ...state, ui: { ...state.ui, isDatabaseModalOpen: false } };
    case "OPEN_DOCUMENT_MODAL":
      return { ...state, ui: { ...state.ui, isDocumentModalOpen: true } };
    case "CLOSE_DOCUMENT_MODAL":
      return { ...state, ui: { ...state.ui, isDocumentModalOpen: false } };
    case "CONNECTION_REQUEST":
      return {
        ...state,
        connection: {
          status: "connecting",
          connectionString: action.payload.connectionString,
          schema: undefined,
          error: undefined,
        },
      };
    case "CONNECTION_SUCCESS":
      return {
        ...state,
        connection: {
          ...state.connection,
          status: "connected",
          schema: action.payload.schema,
          rawSchema: action.payload.rawSchema,
          error: undefined,
        },
      };
    case "CONNECTION_FAILURE":
      return {
        ...state,
        connection: {
          ...state.connection,
          status: "error",
          error: action.payload.error,
        },
      };
    case "RESET_CONNECTION":
      return {
        ...state,
        connection: {
          status: "disconnected",
        },
        documents: [],
        chat: [],
      };
    case "DOCUMENT_UPLOAD_BEGIN": {
      const incoming = action.payload.records.reduce<
        Record<string, DocumentRecord>
      >((acc, record) => {
        acc[record.id] = record;
        return acc;
      }, {});
      const merged = state.documents.map((doc) => incoming[doc.id] ?? doc);
      const newDocs = Object.values(incoming).filter(
        (doc) => !state.documents.find((existing) => existing.id === doc.id)
      );
      return {
        ...state,
        documents: [...merged, ...newDocs],
      };
    }
    case "DOCUMENT_UPLOAD_PROGRESS":
      return {
        ...state,
        documents: state.documents.map((doc) =>
          doc.id === action.payload.id
            ? {
                ...doc,
                progress: action.payload.progress,
                status: "processing",
              }
            : doc
        ),
      };
    case "DOCUMENT_UPLOAD_SUCCESS":
      return {
        ...state,
        documents: state.documents.map((doc) =>
          doc.id === action.payload.id
            ? { ...doc, progress: 100, status: "complete" }
            : doc
        ),
      };
    case "DOCUMENT_UPLOAD_FAILURE":
      return {
        ...state,
        documents: state.documents.map((doc) =>
          doc.id === action.payload.id
            ? { ...doc, status: "error", error: action.payload.error }
            : doc
        ),
      };
    case "ADD_CHAT_MESSAGE":
      return {
        ...state,
        chat: [...state.chat, action.payload.message],
      };
    case "RESET_CHAT":
      return {
        ...state,
        chat: [],
      };
    default:
      return state;
  }
}

const AppStateContext = createContext<AppState | undefined>(undefined);
const AppDispatchContext = createContext<Dispatch<AppAction> | undefined>(
  undefined
);

export function AppStateProvider({
  children,
}: {
  children: ReactNode;
}): ReactElement {
  const [state, dispatch] = useReducer(appReducer, initialState);
  return (
    <AppStateContext.Provider value={state}>
      <AppDispatchContext.Provider value={dispatch}>
        {children}
      </AppDispatchContext.Provider>
    </AppStateContext.Provider>
  );
}

export function useAppState(): AppState {
  const context = useContext(AppStateContext);
  if (!context) {
    throw new Error("useAppState must be used within AppStateProvider");
  }
  return context;
}

export function useAppDispatch(): Dispatch<AppAction> {
  const context = useContext(AppDispatchContext);
  if (!context) {
    throw new Error("useAppDispatch must be used within AppStateProvider");
  }
  return context;
}

export function useAppActions() {
  const dispatch = useAppDispatch();
  return {
    openDatabaseModal: () => dispatch({ type: "OPEN_DATABASE_MODAL" }),
    closeDatabaseModal: () => dispatch({ type: "CLOSE_DATABASE_MODAL" }),
    openDocumentModal: () => dispatch({ type: "OPEN_DOCUMENT_MODAL" }),
    closeDocumentModal: () => dispatch({ type: "CLOSE_DOCUMENT_MODAL" }),
    requestConnection: (connectionString: string) =>
      dispatch({ type: "CONNECTION_REQUEST", payload: { connectionString } }),
    connectionSuccess: (schema: SchemaSummary, rawSchema: BackendSchema) =>
      dispatch({ type: "CONNECTION_SUCCESS", payload: { schema, rawSchema } }),
    connectionFailure: (error: string) =>
      dispatch({ type: "CONNECTION_FAILURE", payload: { error } }),
    resetConnection: () => dispatch({ type: "RESET_CONNECTION" }),
    beginDocumentUpload: (records: DocumentRecord[]) =>
      dispatch({ type: "DOCUMENT_UPLOAD_BEGIN", payload: { records } }),
    documentUploadProgress: (id: string, progress: number) =>
      dispatch({ type: "DOCUMENT_UPLOAD_PROGRESS", payload: { id, progress } }),
    documentUploadSuccess: (id: string) =>
      dispatch({ type: "DOCUMENT_UPLOAD_SUCCESS", payload: { id } }),
    documentUploadFailure: (id: string, error: string) =>
      dispatch({ type: "DOCUMENT_UPLOAD_FAILURE", payload: { id, error } }),
    addChatMessage: (message: ChatMessage) =>
      dispatch({ type: "ADD_CHAT_MESSAGE", payload: { message } }),
    resetChat: () => dispatch({ type: "RESET_CHAT" }),
  };
}

export function createChatMessage(
  partial: Omit<ChatMessage, "id" | "createdAt">
): ChatMessage {
  return {
    id: crypto.randomUUID(),
    createdAt: Date.now(),
    ...partial,
  };
}
