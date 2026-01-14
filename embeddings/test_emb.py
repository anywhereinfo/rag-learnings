import vertexai
from vertexai.language_models import TextEmbeddingModel
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np
from sklearn.decomposition import PCA
import matplotlib.pyplot as plt



vertexai.init(
    project="gcp-prj-ntpc-np-01",
    location="us-central1"
)

# Generate embeddings
model = TextEmbeddingModel.from_pretrained("text-embedding-004")
vec_life = model.get_embeddings(["what is the meaning of life"])[0].values
vec_42 = model.get_embeddings(["42"])[0].values
vec_service = model.get_embeddings(["Existence key purpose is to be of service"])[0].values
vec_service1 = model.get_embeddings(["The meaning of life is to be of service"])[0].values
vec_service2 = model.get_embeddings(["The meaning of life is death"])[0].values
embeddings = [vec_life, vec_42, vec_service, vec_service1, vec_service2]
embeddings_array = np.array(embeddings) 
print("Shape: " + str(embeddings_array.shape))
print(embeddings_array)

#reshape vectors to match cosine similarity
vec_life = np.array(vec_life).reshape(1,-1)
vec_42 = np.array(vec_42).reshape(1,-1)
vec_service =  np.array(vec_service).reshape(1, -1)
vec_service1 =  np.array(vec_service1).reshape(1, -1)
vec_service2 =  np.array(vec_service2).reshape(1, -1)

#cosine similarity
print(f"Similarity with 42: {cosine_similarity(vec_life,vec_42)}")
print(f"Similarity with Existence: {cosine_similarity(vec_life , vec_service)}")
print(f"Similarity with meaning of life: {cosine_similarity(vec_life , vec_service1)}")
print(f"Similarity with death: {cosine_similarity(vec_life , vec_service2)}")

PCA_model = PCA(n_components=2)
PCA_model.fit(embeddings_array)
new_values = PCA_model.transform(embeddings_array) # Shape 5,2
print("Shape: " + str(new_values.shape))
print(new_values)


plt.figure(figsize=(10, 8))
plt.scatter(new_values[:, 0], new_values[:, 1])

labels = [
    "what is the meaning of life",
    "42",
    "Existence key purpose is to be of service",
    "The meaning of life is to be of service",
    "The meaning of life is death"
]

for i, label in enumerate(labels):
    plt.annotate(label, (new_values[i, 0], new_values[i, 1]), xytext=(5, 5), textcoords='offset points')

plt.title("PCA of Text Embeddings")
plt.xlabel("Principal Component 1")
plt.ylabel("Principal Component 2")
plt.grid(True)

# Optional: Use mplcursors if available for interactive usage
try:
    import mplcursors
    mplcursors.cursor(hover=True).connect(
        "add", lambda sel: sel.annotation.set_text(labels[sel.target.index])
    )
except ImportError:
    print("mplcursors not installed. Interactive features disabled.")
except Exception as e:
    print(f"Interactive cursor not available: {e}")

print("Saving plot to pca_embeddings.png")
plt.savefig('pca_embeddings.png')
plt.show()

in_1 = """He couldn’t desert 
          his post at the power plant."""

in_2 = """The power plant needed 
          him at the time."""

in_3 = """Cacti are able to 
          withstand dry environments.""" 

in_4 = """Desert plants can 
          survive droughts.""" 

input_text_lst_sim = [in_1, in_2, in_3, in_4]

embeddings = [
    model.get_embeddings([text])[0].values
    for text in input_text_lst_sim
]

embeddings_arr = np.vstack(embeddings)


for i, item in enumerate(embeddings_arr):
    print(f"Similarity between {input_text_lst_sim[0]} and {input_text_lst_sim[i]} : {cosine_similarity(embeddings_arr[0:1], embeddings_arr[i:i+1])[0][0]}")


print(f"Similarity between {input_text_lst_sim[2]} and {input_text_lst_sim[3]} : {cosine_similarity(embeddings_arr[2:3], embeddings_arr[3:4])[0][0]}")

# Generate Heatmap of Cosine Similarity
sim_matrix = cosine_similarity(embeddings_arr)

plt.figure(figsize=(10, 8))
plt.imshow(sim_matrix, interpolation='nearest', cmap='viridis')
plt.title('Cosine Similarity Heatmap')
plt.colorbar()

# Create labels (clean up newlines and take first few words)
short_labels = [" ".join(text.replace('\n', ' ').split()[:5]) + "..." for text in input_text_lst_sim]

tick_marks = np.arange(len(input_text_lst_sim))
plt.xticks(tick_marks, short_labels, rotation=45, ha='right')
plt.yticks(tick_marks, short_labels)

# Add text annotations
for i in range(sim_matrix.shape[0]):
    for j in range(sim_matrix.shape[1]):
        plt.text(j, i, format(sim_matrix[i, j], '.2f'),
                 horizontalalignment="center",
                 verticalalignment="center",
                 color="white" if sim_matrix[i, j] < 0.7 else "black") # Threshold for text color

plt.tight_layout()
print("Saving heatmap to similarity_heatmap.png")
plt.savefig('similarity_heatmap.png')
plt.show()


