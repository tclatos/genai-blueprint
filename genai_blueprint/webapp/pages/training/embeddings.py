"""Embeddings demo page showing the embedding process with visualization."""

import time

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from genai_tk.core.embeddings_factory import EmbeddingsFactory, get_embeddings
from sklearn.decomposition import PCA
from sklearn.manifold import TSNE
from sklearn.metrics.pairwise import cosine_similarity


def calculate_similarity_matrix(embeddings: list[list[float]]) -> np.ndarray:
    """Calculate cosine similarity matrix between embeddings."""
    return cosine_similarity(embeddings)


def reduce_dimensions(embeddings: list[list[float]], method: str = "PCA") -> np.ndarray:
    """Reduce embedding dimensions for visualization.

    Args:
        embeddings: List of embedding vectors
        method: Dimensionality reduction method ('PCA' or 't-SNE')

    Returns:
        2D array with reduced dimensions
    """
    embeddings_array = np.array(embeddings)

    if method == "PCA":
        reducer = PCA(n_components=2)
    else:  # t-SNE
        reducer = TSNE(n_components=2, random_state=42, perplexity=min(30, len(embeddings) - 1))

    return reducer.fit_transform(embeddings_array)


def create_embedding_plot(embeddings_2d: np.ndarray, texts: list[str], title: str) -> go.Figure:
    """Create interactive plot of embeddings in 2D space."""
    df = pd.DataFrame(
        {
            "x": embeddings_2d[:, 0],
            "y": embeddings_2d[:, 1],
            "text": [text[:50] + "..." if len(text) > 50 else text for text in texts],
            "full_text": texts,
        }
    )

    fig = px.scatter(
        df, x="x", y="y", hover_data=["full_text"], title=title, labels={"x": "Dimension 1", "y": "Dimension 2"}
    )

    # Add text labels
    fig.update_traces(text=df["text"], textposition="middle right", textfont=dict(size=10))

    fig.update_layout(height=500, showlegend=False)

    return fig


def create_similarity_heatmap(similarity_matrix: np.ndarray, texts: list[str]) -> go.Figure:
    """Create heatmap showing similarity between texts."""
    labels = [text[:20] + "..." if len(text) > 20 else text for text in texts]

    fig = go.Figure(
        data=go.Heatmap(
            z=similarity_matrix,
            x=labels,
            y=labels,
            colorscale="Viridis",
            text=np.round(similarity_matrix, 3),
            texttemplate="%{text}",
            textfont={"size": 10},
        )
    )

    fig.update_layout(title="Cosine Similarity Matrix", height=500)

    return fig


def format_embedding_vector(vector: list[float], max_display: int = 10) -> str:
    """Format embedding vector for display."""
    if len(vector) <= max_display:
        return str([round(x, 4) for x in vector])
    else:
        display_vector = [round(x, 4) for x in vector[:max_display]]
        return f"{display_vector}... ({len(vector)} dimensions total)"


# Page configuration
st.set_page_config(
    page_title="Embeddings Demo",
    page_icon="🔢",
    layout="wide",
    initial_sidebar_state="expanded",
)

EXAMPLE_TEXTS = [
    # Basic examples
    "The cat sat on the mat.",
    "A feline rested on a rug.",
    "Dogs are loyal companions.",
    "Python is a programming language.",
    "Machine learning transforms data into insights.",
    "The weather is sunny today.",
    # Animals group
    "Elephants are the largest land mammals.",
    "Birds migrate thousands of miles each year.",
    "Dolphins communicate using complex sounds.",
    # Machine Learning group
    "Neural networks mimic brain structures.",
    "Deep learning requires large datasets.",
    "AI models can recognize patterns in data.",
]

# Initialize session state
if "input_texts" not in st.session_state:
    st.session_state.input_texts = EXAMPLE_TEXTS

if "embeddings_cache" not in st.session_state:
    st.session_state.embeddings_cache = {}

# Main UI
st.title("🔢 Embeddings Demo")
st.markdown("""
Visualize how different embedding models encode text into vector space.

**What are embeddings?** They're mathematical representations of text as lists of numbers (vectors). 
Similar texts get similar numbers, allowing computers to understand meaning and relationships.
""")

# Sidebar for model selection and settings
with st.sidebar:
    st.header("Settings")

    # Get available embeddings models
    try:
        available_models = EmbeddingsFactory.known_items()
        if not available_models:
            st.error("No embedding models available. Please check your API keys and configuration.")
            st.stop()

        selected_model = st.selectbox(
            "Select Embedding Model",
            available_models,
            index=0 if available_models else None,
            help="Choose which AI model to use for converting text to numbers (embeddings)",
        )

        # Model information
        if selected_model:
            try:
                factory = EmbeddingsFactory(embeddings=selected_model)
                model_info = factory.info
                st.info(f"**Provider:** {model_info.provider}\n\n**Model:** {model_info.model}")
                if model_info.dimension:
                    st.info(f"**Dimensions:** {model_info.dimension}")
            except Exception as e:
                st.warning(f"Could not load model info: {e}")

        # Visualization settings
        st.subheader("Visualization")
        cache_embeddings = st.toggle(
            "Cache Embeddings",
            value=False,
            help="Store computed embeddings to avoid recomputing the same texts. Saves time when experimenting.",
        )
    except Exception as e:
        st.error(f"Error loading embedding models: {e}")
        st.stop()

# Main content area
col1, col2 = st.columns([1, 1])

with col1:
    st.header("Text Input")

    # Text input methods
    input_method = st.radio(
        "Input Method",
        ["Text Area", "Individual Texts"],
        help="Text Area: Paste multiple texts at once. Individual Texts: Enter texts one by one for more control.",
    )

    if input_method == "Text Area":
        text_input = st.text_area(
            "Enter texts (one per line):",
            value="\n".join(st.session_state.input_texts),
            height=200,
            key="text_area_input",
            help="Each line becomes a separate text to analyze. Try mixing different topics to see how the AI groups them!",
        )
        texts = [text.strip() for text in text_input.split("\n") if text.strip()]
    else:
        texts = []
        num_texts = st.number_input(
            "Number of texts",
            min_value=1,
            max_value=10,
            value=3,
            help="How many individual text boxes to show for input",
        )
        for i in range(num_texts):
            default_text = st.session_state.input_texts[i] if i < len(st.session_state.input_texts) else ""
            text = st.text_input(f"Text {i + 1}:", value=default_text, key=f"text_{i}")
            if text.strip():
                texts.append(text.strip())

    # Update session state
    if texts != st.session_state.input_texts:
        st.session_state.input_texts = texts

with col2:
    st.header("Quick Actions")

    col2a, col2b = st.columns(2)

    with col2a:
        if st.button("🐾 Animals", help="Load texts about different animals"):
            animal_texts = [
                "The cat sat on the mat.",
                "A feline rested on a rug.",
                "Dogs are loyal companions.",
                "Elephants are the largest land mammals.",
                "Birds migrate thousands of miles each year.",
                "Dolphins communicate using complex sounds.",
            ]
            st.session_state.input_texts = animal_texts
            st.rerun()

        if st.button("🤖 AI/ML", help="Load texts about artificial intelligence and machine learning"):
            ml_texts = [
                "Python is a programming language.",
                "Machine learning transforms data into insights.",
                "Neural networks mimic brain structures.",
                "Deep learning requires large datasets.",
                "AI models can recognize patterns in data.",
            ]
            st.session_state.input_texts = ml_texts
            st.rerun()

    with col2b:
        if st.button("📝 All Samples", help="Load all example texts (mixed topics)"):
            st.session_state.input_texts = EXAMPLE_TEXTS
            st.rerun()

        if st.button("🗑️ Clear All", help="Remove all current texts"):
            st.session_state.input_texts = []
            st.rerun()

    if texts:
        st.metric("Number of Texts", len(texts))

# Process embeddings when we have texts
if texts and selected_model:
    # Create cache key
    cache_key = f"{selected_model}_{hash(tuple(texts))}"

    # Check cache or compute embeddings
    if cache_embeddings and cache_key in st.session_state.embeddings_cache:
        embeddings_data = st.session_state.embeddings_cache[cache_key]
        st.success("Using cached embeddings")
    else:
        with st.spinner("Computing embeddings..."):
            try:
                start_time = time.time()
                embeddings_model = get_embeddings(embeddings=selected_model, cache_embeddings=cache_embeddings)

                # Compute embeddings
                embeddings = embeddings_model.embed_documents(texts)
                processing_time = time.time() - start_time

                embeddings_data = {
                    "embeddings": embeddings,
                    "processing_time": processing_time,
                    "model_info": EmbeddingsFactory(embeddings=selected_model).info,
                }

                # Cache if enabled
                if cache_embeddings:
                    st.session_state.embeddings_cache[cache_key] = embeddings_data

            except Exception as e:
                st.error(f"Error computing embeddings: {e}")
                st.stop()

    embeddings = embeddings_data["embeddings"]
    processing_time = embeddings_data["processing_time"]

    # Display results
    st.header("Results")

    # Metrics
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Texts Processed", len(texts))
        st.caption("Number of texts converted to embeddings")
    with col2:
        st.metric("Vector Dimension", len(embeddings[0]))
        st.caption("How many numbers represent each text (higher = more detailed)")
    with col3:
        st.metric("Processing Time", f"{processing_time:.3f}s")
        st.caption("Time taken to convert texts to embeddings")
    with col4:
        avg_norm = np.mean([np.linalg.norm(emb) for emb in embeddings])
        st.metric("Avg Vector Norm", f"{avg_norm:.3f}")
        st.caption("Average 'strength' of the vectors (mathematical magnitude)")

    # Visualizations
    if len(embeddings) >= 2:
        # Create tabs for different visualization methods
        st.subheader("📊 Visual Representations")

        tab1, tab2 = st.tabs(["PCA Visualization", "t-SNE Visualization"])

        with tab1:
            st.markdown("""
            **PCA (Principal Component Analysis):** Fast, linear method that shows the main directions of variation.
            Good for getting a quick overview of how texts relate to each other.
            """)
            embeddings_2d_pca = reduce_dimensions(embeddings, "PCA")
            fig_scatter_pca = create_embedding_plot(embeddings_2d_pca, texts, "Embeddings Visualization (PCA)")
            st.plotly_chart(fig_scatter_pca, use_container_width=True)

        with tab2:
            st.markdown("""
            **t-SNE (t-Distributed Stochastic Neighbor Embedding):** Better at preserving local relationships and revealing clusters.
            Takes longer to compute but often shows clearer groupings.
            """)
            embeddings_2d_tsne = reduce_dimensions(embeddings, "t-SNE")
            fig_scatter_tsne = create_embedding_plot(embeddings_2d_tsne, texts, "Embeddings Visualization (t-SNE)")
            st.plotly_chart(fig_scatter_tsne, use_container_width=True)

        # Similarity analysis
        st.subheader("🌡️ Similarity Heatmap")
        st.markdown("""
        **How to read this:** Numbers closer to 1.0 mean texts are very similar, closer to 0.0 means very different.
        The diagonal is always 1.0 because each text is identical to itself.
        """)

        similarity_matrix = calculate_similarity_matrix(embeddings)
        fig_heatmap = create_similarity_heatmap(similarity_matrix, texts)
        st.plotly_chart(fig_heatmap, use_container_width=True)

        # Text similarity insights
        st.subheader("🔍 Similarity Insights")
        st.markdown("""
        **What this shows:** The AI model's assessment of which texts are most and least alike in meaning.
        """)

        # Find most and least similar pairs
        n = len(texts)
        max_sim_idx = np.unravel_index(np.argmax(similarity_matrix - np.eye(n)), similarity_matrix.shape)
        min_sim_idx = np.unravel_index(np.argmin(similarity_matrix + np.eye(n)), similarity_matrix.shape)

        col1, col2 = st.columns(2)
        with col1:
            st.success(f"**Most Similar** (score: {similarity_matrix[max_sim_idx]:.3f})")
            st.write(f"• {texts[max_sim_idx[0]]}")
            st.write(f"• {texts[max_sim_idx[1]]}")

        with col2:
            st.error(f"**Least Similar** (score: {similarity_matrix[min_sim_idx]:.3f})")
            st.write(f"• {texts[min_sim_idx[0]]}")
            st.write(f"• {texts[min_sim_idx[1]]}")

    else:
        st.info(
            "📊 **Need more texts for comparisons!** Add at least 2 texts to see similarity visualizations and comparisons."
        )

    # Raw embedding details (always show this section regardless of number of embeddings)
    with st.expander("🔢 Raw Embedding Details - Technical Deep Dive"):
        st.markdown("""
        **For the curious:** Here's what the actual numbers look like and their statistical properties.
        Each text becomes a list of decimal numbers - this is how the AI 'sees' your text.
        """)

        # Text selection for detailed analysis
        text_options = [
            f"Text {i + 1}: {text[:50]}..." if len(text) > 50 else f"Text {i + 1}: {text}"
            for i, text in enumerate(texts)
        ]
        selected_text_idx = st.selectbox(
            "Select text to analyze:",
            range(len(texts)),
            format_func=lambda i: text_options[i],
            help="Choose which text you want to see detailed embedding information for",
        )

        if selected_text_idx is not None:
            text = texts[selected_text_idx]
            embedding = embeddings[selected_text_idx]

            st.subheader(f"Analysis for: {text}")

            col1, col2 = st.columns([1, 2])
            with col1:
                st.metric("Dimensions", len(embedding))
                st.caption("📊 How many numbers in this vector")

                st.metric("L2 Norm", f"{np.linalg.norm(embedding):.4f}")
                st.caption("💪 Overall 'strength' or magnitude of the vector")

                st.metric("Mean Value", f"{np.mean(embedding):.4f}")
                st.caption("📊 Average of all the numbers in the vector")

                st.metric("Std Dev", f"{np.std(embedding):.4f}")
                st.caption("📊 How spread out the numbers are (variation)")

            with col2:
                st.text("Vector Preview:")
                st.caption("🔍 The actual numbers that represent this text")
                st.code(format_embedding_vector(embedding))

                # Show distribution
                st.text("Value Distribution:")
                st.caption("📊 How often different number ranges appear in this vector")
                fig_hist = px.histogram(x=embedding, nbins=50, title=f"Value Distribution - {text[:30]}...")
                fig_hist.update_layout(height=300)
                st.plotly_chart(fig_hist, use_container_width=True)

elif not texts:
    st.info("👆 Enter some texts above to start exploring embeddings!")
else:
    st.error("Please select an embedding model from the sidebar.")
