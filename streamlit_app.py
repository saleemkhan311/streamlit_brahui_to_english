import streamlit as st
import pickle
import re
import string
from string import digits

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel



import torch
from torch.autograd import Variable
from lang import Lang
from EncoderRNN import EncoderRNN
from AttnDecoderRNN import AttnDecoderRNN

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
#print(device)

SOS_token = 0
EOS_token = 1
MAX_LENGTH = 30

# Load language objects
with open('input_lang.pkl', 'rb') as f:
    input_lang = pickle.load(f)

with open('output_lang.pkl', 'rb') as f:
    output_lang = pickle.load(f)

# Function to preprocess text
def preprocess_text(text):
    # Lowercase all characters
    text = text.lower()
    
    # Remove quotes
    text = re.sub("'", '', text)
    
    # Remove all the special characters
    exclude = set(string.punctuation)
    text = ''.join(ch for ch in text if ch not in exclude)
    
    # Remove all numbers from text
    remove_digits = str.maketrans('', '', digits)
    text = text.translate(remove_digits)
    
    # Remove extra spaces
    text = text.strip()
    text = re.sub(" +", " ", text)
    
    return text

def indexesFromSentence(lang, sentence):
    return [lang.word2index[word] for word in sentence.split(' ')]


def tensorFromSentence(lang, sentence):
    indexes = indexesFromSentence(lang, sentence)
    indexes.append(EOS_token)
    return torch.tensor(indexes, dtype=torch.long, device=device).view(-1, 1)


# Function to get variables from string
def variable_from_sentence(lang, sentence):
    indexes = indexesFromSentence(lang, sentence)
    indexes.append(EOS_token)
    var = Variable(torch.LongTensor(indexes).view(-1, 1))
    return var

# Evaluation function
def evaluate(encoder, decoder, sentence, max_length=MAX_LENGTH):
    #print("Input Sentence:", sentence)
    with torch.no_grad():
        input_tensor = tensorFromSentence(input_lang, sentence)
        input_length = input_tensor.size()[0]
        encoder_hidden = encoder.initHidden()

        encoder_outputs = torch.zeros(max_length, encoder.hidden_size, device=device)

        for ei in range(input_length):
            encoder_output, encoder_hidden = encoder(input_tensor[ei],
                                                     encoder_hidden)
            encoder_outputs[ei] += encoder_output[0, 0]

        decoder_input = torch.tensor([[SOS_token]], device=device)  # SOS

        decoder_hidden = encoder_hidden

        decoded_words = []
        decoder_attentions = torch.zeros(max_length, max_length)

        for di in range(max_length):
            decoder_output, decoder_hidden, decoder_attention = decoder(
                decoder_input, decoder_hidden, encoder_outputs)
            decoder_attentions[di] = decoder_attention.data
            topv, topi = decoder_output.data.topk(1)
            if topi.item() == EOS_token:
                decoded_words.append('<EOS>')
                break
            else:
                decoded_words.append(output_lang.index2word[topi.item()])

            decoder_input = topi.squeeze().detach()

            if '<EOS>' in decoded_words:
                decoded_words.remove('<EOS>')

        #print("Decoded Words:", decoded_words)
        return decoded_words, decoder_attentions[:di + 1]
    
attn_model = 'general'
hidden_size = 128
n_layers = 1
dropout_p = 0.05

# Load trained models
encoder = EncoderRNN(input_lang.n_words, hidden_size)
decoder = AttnDecoderRNN(hidden_size, output_lang.n_words, dropout_p=dropout_p)
encoder.load_state_dict(torch.load('model_weights/encoder.pth', map_location='cpu'))
decoder.load_state_dict(torch.load('model_weights/decoder.pth', map_location='cpu'))

def handle_key_error(input_sentence, lang):
    words = input_sentence.split()
    clean_words = []
    for word in words:
        try:
            lang.word2index[word]  # Check if the word exists in the dictionary
            clean_words.append(word)
        except KeyError:
            pass  # Ignore the word if it is not found in the dictionary
    clean_sentence = ' '.join(clean_words)
    #print(input_sentence)
    #print(clean_sentence)
    return clean_sentence

# Streamlit app
def main():
    st.title('Brahui to English Translation App')
    st.write("This is a BETA App Expected Accuracy is around 50%")
    input_text = st.text_area('Enter Brahui Text:', '')
    if st.button('Translate'):
        preprocessed_text = preprocess_text(input_text)
        clean = handle_key_error(preprocessed_text,input_lang)
        output_words, decoder_attn = evaluate(encoder, decoder, clean)
        #print("Output words: ",output_words)
        # Check if each word is a string before joining
        output_text = ' '.join(output_words)
        #st.write('Translated Text:', output_text)
        st.write(f'<div style="font-size: 50px; text-align: center;">{output_text}</div>', unsafe_allow_html=True)

    run_fastapi_app()

    # JavaScript to submit the form when Enter key is pressed
    st.markdown("""
    <script>
    document.addEventListener('DOMContentLoaded', function() {
        document.addEventListener('keypress', function(e) {
            if(e.key === 'Enter') {
                document.querySelector('.streamlit-button').click();
            }
        });
    });
    </script>
    """, unsafe_allow_html=True)

fastapi_app = FastAPI()

class TranslationRequest(BaseModel):
    text: str


@fastapi_app.post("/translate/")
async def translate_text(request: TranslationRequest):
    input_text = request.text
    preprocessed_text = preprocess_text(input_text)
    clean = handle_key_error(preprocessed_text, input_lang)
    output_words, _ = evaluate(encoder, decoder, clean)
    output_text = ' '.join(output_words)
    return {"translated_text": output_text}


def run_fastapi_app():
    import uvicorn
    uvicorn.run(fastapi_app, host="0.0.0.0", port=8080)



if __name__ == '__main__':
    main()
