import {createInferenceGateway} from '../server/inference-gateway.mjs';

// Prefer raw bounded reads when the hosting runtime supports this option.
export const config={api:{bodyParser:false}};
export default createInferenceGateway().generate;
