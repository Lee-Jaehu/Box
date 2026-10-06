import { createContext, useContext } from 'react';

/** 이미지 사용처(task_attachments) 메타데이터. 설명은 사용처에 귀속되며 서버 정식 저장에서 필수 검증된다. */
export interface ImageUse {
  useId: string;
  previewUrl: string;
  title: string;
  description: string;
  fileName: string;
}

export interface ImageContextValue {
  get(useId: string): ImageUse | undefined;
  setMeta(useId: string, patch: Partial<Pick<ImageUse, 'title' | 'description'>>): void;
  /** 업로드 후 사용처를 만든다. 실패하면 throw. */
  upload(file: File): Promise<ImageUse>;
  errors: Record<string, string | undefined>;
}

export const ImageContext = createContext<ImageContextValue | null>(null);
export const useImageContext = () => useContext(ImageContext);
