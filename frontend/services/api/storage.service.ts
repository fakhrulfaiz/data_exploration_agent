import { createClient } from '@/utils/supabase/client';
import { UploadedAttachment } from '@/types/attachments';

const DEFAULT_BUCKET = 'chat-attachments';

const getBucketName = () =>
    process.env.NEXT_PUBLIC_SUPABASE_ATTACHMENTS_BUCKET || DEFAULT_BUCKET;

const buildFilePath = (fileName: string) => {
    const extension = fileName.includes('.') ? fileName.split('.').pop() : undefined;
    const safeExt = extension ? `.${extension}` : '';
    const uuid =
        typeof crypto !== 'undefined' && 'randomUUID' in crypto
            ? crypto.randomUUID()
            : Math.random().toString(36).slice(2);
    return `uploads/${new Date().toISOString().split('T')[0]}/${uuid}${safeExt}`;
};

export async function uploadAttachment(
    file: File
): Promise<UploadedAttachment> {
    const supabase = createClient();
    const bucket = getBucketName();
    const filePath = buildFilePath(file.name);

    const { error } = await supabase.storage
        .from(bucket)
        .upload(filePath, file, {
            cacheControl: '3600',
            upsert: false,
            contentType: file.type || undefined
        });

    if (error) {
        throw new Error(error.message);
    }

    const { data } = supabase.storage
        .from(bucket)
        .getPublicUrl(filePath);

    if (!data?.publicUrl) {
        throw new Error('Unable to generate public URL for attachment');
    }

    return {
        name: file.name,
        size: file.size,
        type: file.type,
        path: filePath,
        url: data.publicUrl
    };
}

export async function uploadAttachments(
    files: File[]
): Promise<UploadedAttachment[]> {
    const uploads: UploadedAttachment[] = [];
    for (const file of files) {
        const uploaded = await uploadAttachment(file);
        uploads.push(uploaded);
    }
    return uploads;
}

export async function deleteAttachment(path: string): Promise<void> {
    const supabase = createClient();
    const bucket = getBucketName();
    const { error } = await supabase.storage.from(bucket).remove([path]);
    if (error) {
        throw new Error(error.message);
    }
}

export async function deleteAttachments(paths: string[]): Promise<void> {
    if (paths.length === 0) return;
    const supabase = createClient();
    const bucket = getBucketName();
    const { error } = await supabase.storage.from(bucket).remove(paths);
    if (error) {
        throw new Error(error.message);
    }
}
