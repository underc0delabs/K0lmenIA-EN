import { z } from 'zod';
import texts from '../i18n/en.json';

export const signupSchema = z.object({
  name: z
    .string()
    .min(2)
    .max(50)
    .regex(/^[A-Za-zÁÉÍÓÚáéíóúÑñ' -]+$/),
  email: z.string().email(),
  username: z
    .string()
    .min(4, texts.longUser)
    .max(20, texts.longUser)
    .regex(/^[A-Za-z0-9_]+$/),
  password: z.string().min(8),
  birthDate: z.coerce.date(),
});

export const MIN_AGE = 18;
