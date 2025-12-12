'use client'

import React from 'react';
import { AlertTriangle } from 'lucide-react';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';

interface DeleteThreadDialogProps {
  isOpen: boolean;
  threadTitle: string;
  onClose: () => void;
  onConfirm: () => void;
}

const DeleteThreadDialog: React.FC<DeleteThreadDialogProps> = ({
  isOpen,
  threadTitle,
  onClose,
  onConfirm
}) => {
  return (
    <AlertDialog open={isOpen} onOpenChange={onClose}>
      <AlertDialogContent className="max-w-md">
        <AlertDialogHeader>
          <div className="flex items-center gap-3 mb-2">
            <div className="w-10 h-10 bg-red-100 dark:bg-red-900/20 rounded-full flex items-center justify-center">
              <AlertTriangle className="w-5 h-5 text-red-600 dark:text-red-400" />
            </div>
            <div>
              <AlertDialogTitle className="text-lg dark:text-white">Delete Thread</AlertDialogTitle>
              <p className="text-sm text-gray-500 dark:text-white">
                This action cannot be undone
              </p>
            </div>
          </div>
        </AlertDialogHeader>

        <AlertDialogDescription className="text-gray-700 dark:text-white">
          Are you sure you want to delete <span className="font-semibold">"{threadTitle}"</span>?
          <span className="block mt-2 text-sm text-gray-500 dark:text-white">
            This will permanently delete the thread and all its messages.
          </span>
        </AlertDialogDescription>

        <AlertDialogFooter>
          <AlertDialogCancel onClick={onClose} className="dark:text-white">Cancel</AlertDialogCancel>
          <AlertDialogAction
            onClick={onConfirm}
            className="bg-red-600 hover:bg-red-700 dark:bg-red-900 dark:hover:bg-red-800 dark:text-white"
          >
            Delete
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
};

export default DeleteThreadDialog;