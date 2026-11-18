import { ImageManipulator, SaveFormat } from 'expo-image-manipulator';
import { MEDIA_LIMITS } from './limits';
import { fitWithin } from './fit';
import type { LocalFile } from './upload';

export interface PickedImage {
  uri: string;
  width: number;
  height: number;
}

/**
 * Shrink a photo on the phone before it is uploaded. A 12-megapixel camera photo is about 4 MB; at the size
 * the model can use it is a few hundred KB, which matters a great deal on a slow or paid connection.
 * The server cleans and checks the picture again: this step only saves time and data.
 */
export async function prepareImage(asset: PickedImage): Promise<LocalFile & { width: number; height: number }> {
  const target = fitWithin(asset.width, asset.height, MEDIA_LIMITS.maxImageEdge);
  const context = ImageManipulator.manipulate(asset.uri);
  if (target.width !== asset.width) context.resize({ width: target.width }); // height follows: the shape is kept
  const image = await context.renderAsync();
  const saved = await image.saveAsync({ format: SaveFormat.JPEG, compress: MEDIA_LIMITS.jpegQuality });
  return { uri: saved.uri, name: 'photo.jpg', mimeType: 'image/jpeg', width: saved.width, height: saved.height };
}
