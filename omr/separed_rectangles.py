from .preprocessor import DocumentProcessor
from .retangles import RectangleDetector
import cv2

def get_retangles(IMAGE_PATH, min_size=100):
    """
    Detecta retângulos na imagem fornecida e retorna os recortes (ROIs) em memória.

    Args:
        IMAGE_PATH (str): Caminho para a imagem de entrada.
        min_size (int): Tamanho mínimo do retângulo.

    Returns:
        list of numpy.ndarray: Lista de imagens ROI (coloridas) dos retângulos detectados.
    """
    import os
    
    print(f"[INFO] Processando a imagem: {IMAGE_PATH}")
    
    # Verifica se o arquivo existe
    if not os.path.exists(IMAGE_PATH):
        print(f"[ERRO] Arquivo não encontrado: {IMAGE_PATH}")
        return []
    
    # Verifica se o arquivo tem conteúdo
    if os.path.getsize(IMAGE_PATH) == 0:
        print(f"[ERRO] Arquivo vazio: {IMAGE_PATH}")
        return []
    
    try:
        # Processamento do documento
        processor = DocumentProcessor(image_path=IMAGE_PATH)
        processor.load_and_resize()
        
        # Verifica se a imagem foi carregada
        if processor.original is None or processor.original.size == 0:
            print(f"[ERRO] Falha ao carregar a imagem: {IMAGE_PATH}")
            return []
        
        processor.correct_perspective()
        
        # Tenta diferentes parâmetros de thresholding para melhor detecção
        # Primeira tentativa com parâmetros padrão
        processor.apply_thresholding(blur_ksize=(5, 5), block_size=11, C=2)
        processor.apply_morphological_closing(kernel_size=4)

        # Verifica se a imagem processada é válida
        if processor.processed_image is None or processor.processed_image.size == 0:
            print(f"[ERRO] Falha no processamento da imagem")
            return []

        # Detecção de retângulos - tenta com diferentes parâmetros
        detector = RectangleDetector(processor.processed_image, min_size=min_size, max_size=2000)
        detector.detect()
        detector.group()
        print(f"[INFO] {len(detector.grouped)} retângulos encontrados com min_size={min_size}.")

        # Se não encontrou retângulos, tenta com diferentes parâmetros
        if len(detector.grouped) == 0:
            print(f"[INFO] Tentando detecção com parâmetros alternativos de thresholding...")
            
            # Tenta com thresholding diferente
            processor.apply_thresholding(blur_ksize=(3, 3), block_size=7, C=3)
            processor.apply_morphological_closing(kernel_size=3)
            detector = RectangleDetector(processor.processed_image, min_size=max(30, min_size // 2), max_size=2000)
            detector.detect()
            detector.group()
            print(f"[INFO] {len(detector.grouped)} retângulos encontrados com parâmetros alternativos.")
            
            # Se ainda não encontrou, tenta detectar diretamente na imagem colorida (warped)
            if len(detector.grouped) == 0:
                print(f"[INFO] Tentando detecção na imagem colorida (sem threshold)...")
                gray_warped = cv2.cvtColor(processor.warped, cv2.COLOR_BGR2GRAY)
                # Aplica threshold simples na imagem colorida
                _, thresh_warped = cv2.threshold(gray_warped, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
                detector = RectangleDetector(thresh_warped, min_size=30, max_size=2000)
                detector.detect()
                detector.group()
                print(f"[INFO] {len(detector.grouped)} retângulos encontrados na imagem colorida.")
            
            # Última tentativa com min_size muito pequeno
            if len(detector.grouped) == 0 and min_size > 30:
                print(f"[INFO] Tentando detecção com min_size mínimo (30)...")
                detector = RectangleDetector(processor.processed_image, min_size=30, max_size=2000)
                detector.detect()
                detector.group()
                print(f"[INFO] {len(detector.grouped)} retângulos encontrados com min_size=30.")

        # Extrai os ROIs coloridos a partir da imagem corrigida
        if len(detector.grouped) == 0:
            print(f"[ERRO] Nenhum retângulo detectado. Verifique a qualidade da imagem e se há retângulos visíveis.")
            return []
        
        color_rois = detector.get_rois(source_img=processor.warped, as_thresh=False)
        
        if not color_rois or len(color_rois) == 0:
            print(f"[ERRO] Falha ao extrair ROIs dos retângulos detectados.")
            return []

        return color_rois
    except Exception as e:
        print(f"[ERRO] Exceção durante processamento: {str(e)}")
        import traceback
        traceback.print_exc()
        return []

if __name__ == "__main__":
    rois = get_retangles("prova5.jpeg", min_size=100)
    for idx, roi in enumerate(rois):
        # por exemplo, exibir com OpenCV:
        cv2.imshow(f"ROI {idx+1}", roi)
    cv2.waitKey(0)


