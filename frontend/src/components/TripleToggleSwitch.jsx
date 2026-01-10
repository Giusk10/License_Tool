import React from "react";
import "./TripleToggleSwitch.css";

const defaultProps = {
    labels: {
        left: { title: "left", value: "left" },
        center: { title: "center", value: "center" },
        right: { title: "right", value: "right" }
    },
    onChange: (value) => console.log("value:", value)
};

class TripleToggleSwitch extends React.Component {
    constructor(props) {
        super(props);
        this.state = {
            switchPosition: "center", // INTENTIONALLY DEFAULT TO CENTER (or props-based if passed later)
            animation: null
        };
    }

    // Consente il controllo dal genitore se necessario, anche se questo componente come scritto dall'utente mantiene il proprio stato.
    // Aggiungeremo componentDidUpdate per sincronizzare se le props cambiano drasticamente, ma atteniamoci principalmente alla struttura della classe dell'utente.
    componentDidMount() {
        // Se le props forniscono un valore iniziale, potremmo impostarlo conformemente.
        // Per ora, ci affideremo alla logica di inizializzazione del genitore o al default 'center' (valore 2).
        if (this.props.value) {
            const pos = this.mapValueToPosition(this.props.value);
            this.setState({ switchPosition: pos });
        }
    }

    componentDidUpdate(prevProps) {
        if (prevProps.value !== this.props.value) {
            const pos = this.mapValueToPosition(this.props.value);
            if (pos !== this.state.switchPosition) {
                // Dobbiamo calcolare l'animazione se vogliamo rigorosamente l'animazione anche sugli aggiornamenti esterni,
                // ma di solito lo stato guida l'animazione. Per un feedback rapido facciamo solo snap o rieseguiamo la logica getSwitchAnimation?
                // Poiché lo script dell'utente `getSwitchAnimation` imposta lo stato E chiama onChange, dovremmo stare attenti a evitare loop.
                // Aggiorneremo solo la posizione senza animazione se controllato esternamente per evitare doppi eventi, o ci fideremo del click interno.
                this.setState({ switchPosition: pos });
            }
        }
    }

     mapValueToPosition(val) {
        if (val === 1 || val === "left") return "left";
        if (val === 2 || val === "center") return "center";
        if (val === 3 || val === "right") return "right";
        return "center";
    }

    getSwitchAnimation = (value) => {
        const { switchPosition } = this.state;
        let animation = null;
        if (value === "center" && switchPosition === "left") {
            animation = "left-to-center";
        } else if (value === "right" && switchPosition === "center") {
            animation = "center-to-right";
        } else if (value === "center" && switchPosition === "right") {
            animation = "right-to-center";
        } else if (value === "left" && switchPosition === "center") {
            animation = "center-to-left";
        } else if (value === "right" && switchPosition === "left") {
            animation = "left-to-right";
        } else if (value === "left" && switchPosition === "right") {
            animation = "right-to-left";
        }

        this.props.onChange(value);
        this.setState({ switchPosition: value, animation });
    };

    /**
     * Metodo render - Renderizza il componente
     *
     * Struttura del componente:
     * - Un div contenitore principale (main-container)
     * - Un div animato che rappresenta lo slider visivo (switch)
     * - Tre input radio nascosti (per accessibilità e funzionalità)
     * - Tre label cliccabili che fungono da pulsanti visibili
     *
     * L'uso di radio buttons nativi garantisce:
     * - Accessibilità da tastiera
     * - Supporto per screen reader
     * - Comportamento nativo del browser
     */
    render() {
        // Estrae le etichette dalle props
        const { labels } = this.props;

        return (
            <div className="main-container">
                {/* Slider visivo che si muove con le animazioni CSS */}
                <div
                    className={`switch ${this.state.animation} ${this.state.switchPosition}-position`}
                ></div>

                {/* INPUT E LABEL SINISTRA */}
                {/* Radio button nascosto per la posizione sinistra */}
                <input
                    onChange={(e) => this.getSwitchAnimation(e.target.value)}
                    name="map-switch"
                    id="left"
                    type="radio"
                    value="left"
                    checked={this.state.switchPosition === "left"}
                />
                {/* Label cliccabile che attiva il radio button */}
                <label
                    className={`left-label ${this.state.switchPosition === "left" && "black-font"
                        }`}
                    htmlFor="left"
                >
                    <h4>{labels.left.title}</h4>
                </label>

                {/* INPUT E LABEL CENTRO */}
                {/* Radio button nascosto per la posizione centrale */}
                <input
                    onChange={(e) => this.getSwitchAnimation(e.target.value)}
                    name="map-switch"
                    id="center"
                    type="radio"
                    value="center"
                    checked={this.state.switchPosition === "center"}
                />
                {/* Label cliccabile che attiva il radio button */}
                <label
                    className={`center-label ${this.state.switchPosition === "center" && "black-font"
                        }`}
                    htmlFor="center"
                >
                    <h4>{labels.center.title}</h4>
                </label>

                {/* INPUT E LABEL DESTRA */}
                {/* Radio button nascosto per la posizione destra */}
                <input
                    onChange={(e) => this.getSwitchAnimation(e.target.value)}
                    name="map-switch"
                    id="right"
                    type="radio"
                    value="right"
                    checked={this.state.switchPosition === "right"}
                />
                {/* Label cliccabile che attiva il radio button */}
                <label
                    className={`right-label ${this.state.switchPosition === "right" && "black-font"
                        }`}
                    htmlFor="right"
                >
                    <h4>{labels.right.title}</h4>
                </label>
            </div>
        );
    }
}

// Assegna le props di default al componente
TripleToggleSwitch.defaultProps = defaultProps;

// Esporta il componente per l'uso in altre parti dell'applicazione
export default TripleToggleSwitch;
